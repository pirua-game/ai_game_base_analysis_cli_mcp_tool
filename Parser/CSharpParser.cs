using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using gdep.Graph;

namespace gdep.Parser;

public record ParsedEdge(string To, EdgeKind Kind, string MemberName);

public record MethodInfo(
    string Name,
    string ReturnType,
    List<string> Parameters,
    bool IsAsync,
    bool IsPublic,
    bool IsOverride,
    bool IsVirtual,
    bool IsStatic
);

public record FieldInfo(
    string Name,
    string TypeName,
    bool IsPublic,
    bool IsStatic,
    bool IsReadOnly,
    EdgeKind Kind  // Field or Property
);

public class ParsedType
{
    public ClassNode Node { get; set; } = new();
    public List<ParsedEdge> Edges { get; set; } = new();
    public List<MethodInfo> Methods { get; set; } = new();
    public List<FieldInfo> Fields { get; set; } = new();
    public string TypeKind { get; set; } = "class"; // class, struct, interface
}

public class CSharpParser
{
    private static readonly HashSet<string> Primitives = new()
    {
        "void", "string", "int", "float", "bool", "double", "long",
        "byte", "char", "object", "var", "String", "Int32", "Single",
        "Boolean", "Double", "Byte", "Char", "Object", "Task",
        "IEnumerable", "IList", "ICollection", "Action", "Func",
        "List", "Dictionary", "HashSet", "Queue", "Stack", "Array",
        "GameObject", "Transform", "MonoBehaviour", "ScriptableObject",
        "Component", "Coroutine", "Vector2", "Vector3", "Quaternion",
        "Color", "Rect", "LayerMask", "AnimationClip", "Sprite",
        "IDisposable", "EventHandler", "Delegate", "UniTask", "UniTaskVoid",
    };

    // 여러 파일 병합 (partial class 대응)
    public List<ParsedType> ParseFiles(IEnumerable<string> filePaths, bool deep = false)
    {
        var mergedNodes   = new Dictionary<string, ClassNode>();
        var mergedEdges   = new Dictionary<string, List<ParsedEdge>>();
        var mergedMethods = new Dictionary<string, List<MethodInfo>>();
        var mergedFields  = new Dictionary<string, List<FieldInfo>>();
        var mergedKind    = new Dictionary<string, string>();

        foreach (var filePath in filePaths)
        {
            foreach (var parsed in ParseFile(filePath, deep))
            {
                var key = $"{parsed.Node.Namespace}.{parsed.Node.Name}";

                if (!mergedNodes.ContainsKey(key))
                {
                    mergedNodes[key]   = parsed.Node;
                    mergedEdges[key]   = new List<ParsedEdge>();
                    mergedMethods[key] = new List<MethodInfo>();
                    mergedFields[key]  = new List<FieldInfo>();
                    mergedKind[key]    = parsed.TypeKind;
                }
                else
                {
                    foreach (var bt in parsed.Node.BaseTypes)
                        if (!mergedNodes[key].BaseTypes.Contains(bt))
                            mergedNodes[key].BaseTypes.Add(bt);
                }

                mergedEdges[key].AddRange(parsed.Edges);
                mergedMethods[key].AddRange(parsed.Methods);
                mergedFields[key].AddRange(parsed.Fields);
            }
        }

        return mergedNodes.Keys.Select(k => new ParsedType
        {
            Node     = mergedNodes[k],
            Edges    = mergedEdges[k],
            Methods  = mergedMethods[k],
            Fields   = mergedFields[k],
            TypeKind = mergedKind[k],
        }).ToList();
    }

    public List<ParsedType> ParseFile(string filePath, bool deep = false)
    {
        var results = new List<ParsedType>();

        string code;
        try { code = File.ReadAllText(filePath); }
        catch { return results; }

        var tree = CSharpSyntaxTree.ParseText(code);
        var root = tree.GetCompilationUnitRoot();

        var ns = root.DescendantNodes()
            .OfType<BaseNamespaceDeclarationSyntax>()
            .FirstOrDefault()?.Name.ToString() ?? "";

        var typeDecls = root.DescendantNodes()
            .Where(n => n is ClassDeclarationSyntax
                     or InterfaceDeclarationSyntax
                     or StructDeclarationSyntax);

        foreach (var decl in typeDecls)
        {
            var node = new ClassNode { FilePath = filePath, Namespace = ns };
            var edges   = new List<ParsedEdge>();
            var methods = new List<MethodInfo>();
            var fields  = new List<FieldInfo>();
            var kind    = "class";

            switch (decl)
            {
                case ClassDeclarationSyntax cls:
                    node.Name = cls.Identifier.Text;
                    kind = "class";
                    ExtractBaseTypes(cls.BaseList, node, edges);
                    ExtractMemberEdges(cls, edges);
                    ExtractMethods(cls, methods);
                    ExtractFields(cls, fields);
                    if (deep) ExtractDeepEdges(cls, edges);
                    break;
                case InterfaceDeclarationSyntax iface:
                    node.Name = iface.Identifier.Text;
                    kind = "interface";
                    ExtractBaseTypes(iface.BaseList, node, edges);
                    ExtractMemberEdges(iface, edges);
                    ExtractMethods(iface, methods);
                    break;
                case StructDeclarationSyntax strct:
                    node.Name = strct.Identifier.Text;
                    kind = "struct";
                    ExtractBaseTypes(strct.BaseList, node, edges);
                    ExtractMemberEdges(strct, edges);
                    ExtractMethods(strct, methods);
                    ExtractFields(strct, fields);
                    if (deep) ExtractDeepEdges(strct, edges);
                    break;
            }

            if (!string.IsNullOrEmpty(node.Name))
                results.Add(new ParsedType
                {
                    Node = node, Edges = edges,
                    Methods = methods, Fields = fields, TypeKind = kind
                });
        }

        return results;
    }

    private void ExtractDeepEdges(SyntaxNode typeDecl, List<ParsedEdge> edges)
    {
        var methodBodies = typeDecl.DescendantNodes()
            .Where(n => n is MethodDeclarationSyntax
                     or ConstructorDeclarationSyntax
                     or AccessorDeclarationSyntax);

        foreach (var bodyOwner in methodBodies)
        {
            SyntaxNode? body = bodyOwner switch
            {
                MethodDeclarationSyntax m => (SyntaxNode?)m.Body ?? m.ExpressionBody,
                ConstructorDeclarationSyntax c => (SyntaxNode?)c.Body ?? c.ExpressionBody,
                AccessorDeclarationSyntax a => (SyntaxNode?)a.Body ?? a.ExpressionBody,
                _ => null
            };

            if (body == null) continue;

            // 1. 객체 생성 (new ClassName())
            foreach (var creation in body.DescendantNodes().OfType<ObjectCreationExpressionSyntax>())
            {
                foreach (var typeName in ExtractAllTypeNames(creation.Type.ToString()))
                    edges.Add(new ParsedEdge(typeName, EdgeKind.Parameter, "new"));
            }

            // 2. 정적 멤버 접근 / 싱글톤 (ClassName.Instance)
            foreach (var memberAccess in body.DescendantNodes().OfType<MemberAccessExpressionSyntax>())
            {
                var receiver = memberAccess.Expression.ToString();
                if (!string.IsNullOrEmpty(receiver) && char.IsUpper(receiver[0])) // 클래스명으로 추정
                {
                    if (!Primitives.Contains(receiver))
                        edges.Add(new ParsedEdge(receiver, EdgeKind.Parameter, "static_access"));
                }
            }

            // 3. 지역 변수 선언 (ClassName varName = ...)
            foreach (var varDecl in body.DescendantNodes().OfType<VariableDeclarationSyntax>())
            {
                foreach (var typeName in ExtractAllTypeNames(varDecl.Type.ToString()))
                    edges.Add(new ParsedEdge(typeName, EdgeKind.Parameter, "local_var"));
            }
        }
    }

    private void ExtractMethods(SyntaxNode decl, List<MethodInfo> methods)
    {
        // 직접 자식 메서드만 (중첩 클래스 내부 제외)
        var directMethods = decl.ChildNodes()
            .OfType<MethodDeclarationSyntax>()
            .ToList();

        foreach (var method in directMethods)
        {
            var modifiers = method.Modifiers.Select(m => m.Text).ToList();
            var isAsync   = modifiers.Contains("async");
            var isPublic  = modifiers.Contains("public");
            var isOverride = modifiers.Contains("override");
            var isVirtual  = modifiers.Contains("virtual");
            var isStatic   = modifiers.Contains("static");

            var parameters = method.ParameterList.Parameters
                .Select(p => $"{ShortTypeName(p.Type?.ToString() ?? "")} {p.Identifier.Text}")
                .ToList();

            methods.Add(new MethodInfo(
                Name: method.Identifier.Text,
                ReturnType: ShortTypeName(method.ReturnType.ToString()),
                Parameters: parameters,
                IsAsync: isAsync,
                IsPublic: isPublic,
                IsOverride: isOverride,
                IsVirtual: isVirtual,
                IsStatic: isStatic
            ));
        }
    }

    private void ExtractFields(SyntaxNode decl, List<FieldInfo> fields)
    {
        // 필드
        foreach (var field in decl.ChildNodes().OfType<FieldDeclarationSyntax>())
        {
            var modifiers = field.Modifiers.Select(m => m.Text).ToList();
            foreach (var variable in field.Declaration.Variables)
            {
                fields.Add(new FieldInfo(
                    Name: variable.Identifier.Text,
                    TypeName: ShortTypeName(field.Declaration.Type.ToString()),
                    IsPublic: modifiers.Contains("public"),
                    IsStatic: modifiers.Contains("static"),
                    IsReadOnly: modifiers.Contains("readonly"),
                    Kind: EdgeKind.Field
                ));
            }
        }

        // 프로퍼티
        foreach (var prop in decl.ChildNodes().OfType<PropertyDeclarationSyntax>())
        {
            var modifiers = prop.Modifiers.Select(m => m.Text).ToList();
            fields.Add(new FieldInfo(
                Name: prop.Identifier.Text,
                TypeName: ShortTypeName(prop.Type.ToString()),
                IsPublic: modifiers.Contains("public"),
                IsStatic: modifiers.Contains("static"),
                IsReadOnly: prop.AccessorList?.Accessors.All(a =>
                    a.Keyword.Text != "set") ?? false,
                Kind: EdgeKind.Property
            ));
        }
    }

    private void ExtractBaseTypes(BaseListSyntax? baseList, ClassNode node, List<ParsedEdge> edges)
    {
        if (baseList == null) return;
        foreach (var t in baseList.Types)
        {
            // Use raw type name for inheritance — never filter base types through Primitives,
            // because engine base classes (MonoBehaviour, ScriptableObject, etc.) must be preserved.
            var raw = t.Type.ToString();
            var name = raw.Split('<')[0].Trim();
            if (name.Contains('.')) name = name.Split('.').Last();
            if (string.IsNullOrEmpty(name)) continue;
            node.BaseTypes.Add(name);
            edges.Add(new ParsedEdge(name, EdgeKind.Inheritance, ""));
        }
    }

    private void ExtractMemberEdges(SyntaxNode decl, List<ParsedEdge> edges)
    {
        foreach (var field in decl.DescendantNodes().OfType<FieldDeclarationSyntax>())
        {
            var memberName = field.Declaration.Variables.FirstOrDefault()?.Identifier.Text ?? "";
            foreach (var typeName in ExtractAllTypeNames(field.Declaration.Type.ToString()))
                edges.Add(new ParsedEdge(typeName, EdgeKind.Field, memberName));
        }

        foreach (var prop in decl.DescendantNodes().OfType<PropertyDeclarationSyntax>())
        {
            foreach (var typeName in ExtractAllTypeNames(prop.Type.ToString()))
                edges.Add(new ParsedEdge(typeName, EdgeKind.Property, prop.Identifier.Text));
        }

        foreach (var method in decl.DescendantNodes().OfType<MethodDeclarationSyntax>())
        {
            var memberName = method.Identifier.Text;
            foreach (var typeName in ExtractAllTypeNames(method.ReturnType.ToString()))
                edges.Add(new ParsedEdge(typeName, EdgeKind.Parameter, memberName));
            foreach (var param in method.ParameterList.Parameters)
                foreach (var typeName in ExtractAllTypeNames(param.Type?.ToString() ?? ""))
                    edges.Add(new ParsedEdge(typeName, EdgeKind.Parameter,
                        $"{memberName}({param.Identifier.Text})"));
        }
    }

    private IEnumerable<string> ExtractAllTypeNames(string typeStr)
    {
        var tokens = typeStr
            .Split(['<', '>', ',', '?', '[', ']', ' '], StringSplitOptions.RemoveEmptyEntries);
        foreach (var token in tokens)
        {
            var simple = token.Trim();
            if (simple.Contains('.')) simple = simple.Split('.').Last();
            if (!string.IsNullOrEmpty(simple) && !Primitives.Contains(simple))
                yield return simple;
        }
    }

    private string ShortTypeName(string typeName)
    {
        // 긴 네임스페이스 prefix 제거, 제네릭 단순화
        return typeName.Replace("System.Collections.Generic.", "")
                       .Replace("System.Threading.Tasks.", "");
    }

    private string CleanTypeName(string typeName)
    {
        var simple = typeName.Split('<')[0].Trim();
        if (simple.Contains('.')) simple = simple.Split('.').Last();
        return Primitives.Contains(simple) ? "" : simple;
    }
}