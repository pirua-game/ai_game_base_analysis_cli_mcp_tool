using System.Text.Json;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Spectre.Console;
using gdep.Parser;

namespace gdep.Commands;

public class HintsCommand
{
    private readonly MethodCallAnalyzer _analyzer = new();

    // 힌트 파일 자동 생성
    public void Generate(string path, string? outputFile = null, bool skipProto = true,
        string[]? ignorePatterns = null)
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            return;
        }

        var csFiles = ScanCommand.CollectFiles(path, skipProto, ignorePatterns);

        AnsiConsole.Progress().Start(ctx =>
        {
            var t = ctx.AddTask("[teal]Analyzing code...[/]", maxValue: 1);
            _analyzer.BuildIndex(csFiles);
            t.Value = 1;
        });

        var knownClasses = _analyzer.GetKnownClasses();

        // Static/Singleton candidate detection:
        // Properties with types in KnownClasses → candidates for chain access
        var candidates = new Dictionary<string, Dictionary<string, string>>();

        // Method 1: Directly analyze "ClassName.Property.Method()" patterns from scanned files
        var chainPatterns = ExtractChainPatterns(csFiles, knownClasses);
        foreach (var (cls, props) in chainPatterns)
        {
            if (!candidates.ContainsKey(cls))
                candidates[cls] = new Dictionary<string, string>();
            foreach (var (prop, type) in props)
                candidates[cls].TryAdd(prop, type);
        }

        // Method 2: Existing StaticAccessors (automatically detected from index)
        _analyzer.AutoDetectStaticAccessors();
        foreach (var (cls, props) in _analyzer.GetStaticAccessors())
        {
            if (!candidates.ContainsKey(cls))
                candidates[cls] = new Dictionary<string, string>();
            foreach (var (prop, type) in props)
                candidates[cls].TryAdd(prop, type);
        }

        // Output and save results
        AnsiConsole.WriteLine();
        AnsiConsole.MarkupLine($"[teal]── Hint candidates detected[/]");

        var hints = new GdepHints { StaticAccessors = candidates };

        if (candidates.Count == 0)
        {
            AnsiConsole.MarkupLine("[gray]No candidates automatically detected. Please add hints manually.[/]");
        }
        else
        {
            var table = new Table()
                .Border(TableBorder.Simple)
                .AddColumn("Class")
                .AddColumn("Property")
                .AddColumn("Type");

            foreach (var (cls, props) in candidates.OrderBy(x => x.Key))
                foreach (var (prop, type) in props.OrderBy(x => x.Key))
                    table.AddRow(Markup.Escape(cls), Markup.Escape(prop), Markup.Escape(type));

            AnsiConsole.Write(table);
        }

        // JSON serialization
        var json = JsonSerializer.Serialize(hints, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        });

        var outPath = outputFile ?? Path.Combine(path, ".gdep-hints.json");
        File.WriteAllText(outPath, json);

        AnsiConsole.WriteLine();
        AnsiConsole.MarkupLine($"[green]Hint file saved:[/] {outPath}");
        AnsiConsole.MarkupLine("[gray]You can open the file and add missing entries manually.[/]");
        AnsiConsole.MarkupLine("[gray]Example: \"Managers\": {{ \"UI\": \"ManagerUI\", \"Sound\": \"ManagerSound\" }}[/]");
    }

    // Check current hint file status
    public void Show(string path)
    {
        // 1순위: path부터 위로 탐색하며 .gdep/.gdep-hints.json 탐색 (프로젝트 루트)
        var candidates = new List<string>();
        var dir = new DirectoryInfo(Path.GetFullPath(path));
        while (dir != null)
        {
            candidates.Add(Path.Combine(dir.FullName, ".gdep", ".gdep-hints.json"));
            dir = dir.Parent;
        }
        // 2순위: 레거시 위치 (이전 버전 호환)
        candidates.Add(Path.Combine(path, ".gdep-hints.json"));
        candidates.Add(Path.Combine(Directory.GetCurrentDirectory(), ".gdep-hints.json"));

        foreach (var hintPath in candidates)
        {
            if (!File.Exists(hintPath)) continue;

            AnsiConsole.MarkupLine($"[gray]Hint file: {hintPath}[/]\n");

            var json = File.ReadAllText(hintPath);
            var hints = JsonSerializer.Deserialize<GdepHints>(json,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

            if (hints?.StaticAccessors == null || !hints.StaticAccessors.Any())
            {
                AnsiConsole.MarkupLine("[gray]No hints registered.[/]");
                return;
            }

            var table = new Table()
                .Border(TableBorder.Simple)
                .AddColumn("Class")
                .AddColumn("Property")
                .AddColumn("Mapped Type");

            foreach (var (cls, props) in hints.StaticAccessors.OrderBy(x => x.Key))
                foreach (var (prop, type) in props.OrderBy(x => x.Key))
                    table.AddRow(Markup.Escape(cls), Markup.Escape(prop), Markup.Escape(type));

            AnsiConsole.Write(table);
            AnsiConsole.MarkupLine($"\n[gray]Total {hints.StaticAccessors.Count} classes · " +
                $"{hints.StaticAccessors.Values.Sum(p => p.Count)} mappings[/]");
            return;
        }

        AnsiConsole.MarkupLine("[yellow]Hint file not found.[/]");
        AnsiConsole.MarkupLine("[gray]You can generate one automatically using 'gdep hints generate <path>'.[/]");
    }

    // ── Extract chain patterns with AST ──────────────────────────────────

    private Dictionary<string, Dictionary<string, string>> ExtractChainPatterns(
        string[] filePaths, IReadOnlySet<string> knownClasses)
    {
        var result = new Dictionary<string, Dictionary<string, string>>();

        foreach (var filePath in filePaths)
        {
            string code;
            try { code = File.ReadAllText(filePath); }
            catch { continue; }

            var tree = CSharpSyntaxTree.ParseText(code);
            var root = tree.GetCompilationUnitRoot();

            // Detect A.B.Method() pattern: MemberAccess(MemberAccess(A, B), Method)
            foreach (var inv in root.DescendantNodes().OfType<InvocationExpressionSyntax>())
            {
                if (inv.Expression is not MemberAccessExpressionSyntax outerAccess) continue;
                if (outerAccess.Expression is not MemberAccessExpressionSyntax innerAccess) continue;

                // innerAccess = A.B  (A=ClassName, B=PropertyName)
                var className = innerAccess.Expression is IdentifierNameSyntax id ? id.Identifier.Text : null;
                var propName  = innerAccess.Name.Identifier.Text;
                var methodName = outerAccess.Name.Identifier.Text;

                if (className == null) continue;

                // Skip if A is already a known class (field chains are already handled)
                if (knownClasses.Contains(className)) continue;

                // To infer the actual type through B, we need to find the B type in the codebase
                // Here we only record the pattern and keep the type empty → user fills it
                if (!result.ContainsKey(className))
                    result[className] = new Dictionary<string, string>();

                // Add only items with empty values (to be filled by user)
                result[className].TryAdd(propName, $"/* Enter {propName} type here */");
            }
        }

        // 값이 전부 주석인 클래스만 남김 (자동 해결 불가 후보)
        return result
            .Where(kv => kv.Value.Any())
            .ToDictionary(kv => kv.Key, kv => kv.Value);
    }
}