using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Spectre.Console;

namespace gdep.Commands;

public record LintIssue(
    string RuleId,
    string Severity,
    string Message,
    string Class,
    string Method,
    string File,
    string Suggestion
);

public class LintCommand
{
    private static readonly HashSet<string> LifecycleMethods = new()
    {
        "Update", "FixedUpdate", "LateUpdate"
    };

    private static readonly HashSet<string> HeavyInvocations = new()
    {
        "GetComponent", "Find", "FindGameObjectWithTag", "FindWithTag",
        "FindObjectsOfType", "FindObjectOfType"
    };

    // Heavy static property accesses (e.g. Camera.main calls FindObjectOfType internally)
    private static readonly Dictionary<string, string> HeavyStaticProperties = new()
    {
        { "Camera.main", "UNI-PERF-001" }
    };

    public void Execute(string path, string[]? ignorePatterns = null, bool skipProto = true)
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            return;
        }

        var csFiles = ScanCommand.CollectFiles(path, skipProto, ignorePatterns);
        var issues = new List<LintIssue>();

        foreach (var file in csFiles)
        {
            AnalyzeFile(file, issues);
        }

        var json = JsonSerializer.Serialize(issues, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        });

        Console.WriteLine(json);
    }

    private void AnalyzeFile(string filePath, List<LintIssue> issues)
    {
        string code;
        try { code = File.ReadAllText(filePath); }
        catch { return; }

        var tree = CSharpSyntaxTree.ParseText(code,
            CSharpParseOptions.Default.WithPreprocessorSymbols(
                "UNITY_EDITOR", "UNITY_STANDALONE", "UNITY_ANDROID", "UNITY_IOS",
                "UNITY_2019_1_OR_NEWER", "UNITY_2020_1_OR_NEWER", "UNITY_2021_1_OR_NEWER"
            ));
        var root = tree.GetCompilationUnitRoot();

        var classDecls = root.DescendantNodes().OfType<ClassDeclarationSyntax>();

        foreach (var cls in classDecls)
        {
            var className = cls.Identifier.Text;

            // Build method lookup for 1-level helper call tracing
            var allMethods = cls.DescendantNodes()
                .OfType<MethodDeclarationSyntax>()
                .GroupBy(m => m.Identifier.Text)
                .ToDictionary(g => g.Key, g => g.First());

            var methods = cls.DescendantNodes().OfType<MethodDeclarationSyntax>();

            foreach (var method in methods)
            {
                var methodName = method.Identifier.Text;
                if (!LifecycleMethods.Contains(methodName)) continue;

                var body = (SyntaxNode?)method.Body ?? method.ExpressionBody;
                if (body == null) continue;

                // Scan lifecycle body + 1-level helper method bodies
                var bodiesToScan = new List<(SyntaxNode scanBody, string context)>
                {
                    (body, methodName)
                };

                foreach (var invocation in body.DescendantNodes().OfType<InvocationExpressionSyntax>())
                {
                    var calledName = GetMethodName(invocation);
                    if (!string.IsNullOrEmpty(calledName)
                        && allMethods.TryGetValue(calledName, out var helperMethod))
                    {
                        var helperBody = (SyntaxNode?)helperMethod.Body ?? helperMethod.ExpressionBody;
                        if (helperBody != null)
                            bodiesToScan.Add((helperBody, $"{methodName}>{calledName}"));
                    }
                }

                foreach (var (scanBody, context) in bodiesToScan)
                {
                    // 1. Heavy Invocations (GetComponent, Find, FindObjectOfType, etc.)
                    foreach (var invocation in scanBody.DescendantNodes().OfType<InvocationExpressionSyntax>())
                    {
                        var name = GetMethodName(invocation);
                        if (HeavyInvocations.Contains(name))
                        {
                            issues.Add(new LintIssue(
                                RuleId: "UNI-PERF-001",
                                Severity: "Warning",
                                Message: $"Heavy operation '{name}' detected in {context}().",
                                Class: className,
                                Method: methodName,
                                File: Path.GetFileName(filePath),
                                Suggestion: "Cache the reference in Awake() or Start() instead."
                            ));
                        }
                    }

                    // 2. Object Allocations (Instantiate / new T)
                    foreach (var invocation in scanBody.DescendantNodes().OfType<InvocationExpressionSyntax>())
                    {
                        var name = GetMethodName(invocation);
                        if (name == "Instantiate")
                        {
                            issues.Add(new LintIssue(
                                RuleId: "UNI-PERF-002",
                                Severity: "Warning",
                                Message: $"Object instantiation (Instantiate) detected in {context}().",
                                Class: className,
                                Method: methodName,
                                File: Path.GetFileName(filePath),
                                Suggestion: "Consider using Object Pooling for frequently spawned objects."
                            ));
                        }
                    }

                    foreach (var creation in scanBody.DescendantNodes().OfType<ObjectCreationExpressionSyntax>())
                    {
                        var typeName = creation.Type.ToString();
                        if (typeName is "Vector2" or "Vector3" or "Vector4" or "Quaternion" or "Color" or "Ray")
                            continue;

                        issues.Add(new LintIssue(
                            RuleId: "UNI-PERF-002",
                            Severity: "Warning",
                            Message: $"Memory allocation (new {typeName}) detected in {context}().",
                            Class: className,
                            Method: methodName,
                            File: Path.GetFileName(filePath),
                            Suggestion: "Avoid frequent allocations in Update to prevent GC spikes. Use a pool or cache the object."
                        ));
                    }

                    // 3. Heavy static property accesses (e.g. Camera.main)
                    foreach (var memberAccess in scanBody.DescendantNodes().OfType<MemberAccessExpressionSyntax>())
                    {
                        var ownerName = memberAccess.Expression.ToString();
                        var propName  = memberAccess.Name.Identifier.Text;
                        var key = $"{ownerName}.{propName}";
                        if (HeavyStaticProperties.ContainsKey(key))
                        {
                            issues.Add(new LintIssue(
                                RuleId: "UNI-PERF-001",
                                Severity: "Warning",
                                Message: $"Heavy static property '{key}' accessed in {context}(). " +
                                         "Camera.main internally calls FindObjectOfType on every access.",
                                Class: className,
                                Method: methodName,
                                File: Path.GetFileName(filePath),
                                Suggestion: "Cache Camera.main in Awake() or Start() and reuse the reference."
                            ));
                        }
                    }
                } // end bodiesToScan
            }
        }
    }

    private string GetMethodName(InvocationExpressionSyntax invocation)
    {
        if (invocation.Expression is IdentifierNameSyntax id)
            return id.Identifier.Text;

        if (invocation.Expression is MemberAccessExpressionSyntax member)
            return member.Name.Identifier.Text;

        if (invocation.Expression is GenericNameSyntax generic)
            return generic.Identifier.Text;

        return "";
    }
}
