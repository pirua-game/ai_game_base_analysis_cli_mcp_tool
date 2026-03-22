using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace gdep.Parser;

// ── 데이터 모델 ────────────────────────────────────────────────

public record CallNode(
    string ClassName,
    string MethodName,
    bool IsAsync = false,
    bool IsExternal = false,
    bool IsHandlerDispatch = false
)
{
    public string Id => $"{ClassName}.{MethodName}".Replace('<', '_').Replace('>', '_');
    public string Label => IsHandlerDispatch
        ? $"[handler] {ClassName}.{MethodName}"
        : $"{ClassName}.{MethodName}";
}

public record CallEdge(
    CallNode From,
    CallNode To,
    string? Note = null,
    bool IsDynamic = false
);

public class CallGraph
{
    public List<CallNode> Nodes { get; } = new();
    public List<CallEdge> Edges { get; } = new();
    private readonly HashSet<string> _nodeIds = new();

    public void AddNode(CallNode node)
    {
        if (_nodeIds.Add(node.Id))
            Nodes.Add(node);
    }

    public void AddEdge(CallEdge edge) => Edges.Add(edge);
}

// ── 힌트 모델 ─────────────────────────────────────────────────

public class GdepHints
{
    // 정적/싱글톤 클래스의 프로퍼티→타입 매핑
    // 예: "Managers" → { "UI": "ManagerUI", "Sound": "ManagerSound" }
    public Dictionary<string, Dictionary<string, string>> StaticAccessors { get; set; } = new();
}

// ── 메서드 인덱스 ─────────────────────────────────────────────

public class MethodIndex
{
    public readonly Dictionary<(string, string), List<MethodDeclarationSyntax>> Methods = new();
    public readonly Dictionary<string, Dictionary<string, string>> MemberTypes = new();
    public readonly Dictionary<string, Dictionary<string, string>> ReturnTypes = new();
    public readonly HashSet<string> KnownClasses = new();

    // 힌트에서 로드된 정적 접근자 맵
    public readonly Dictionary<string, Dictionary<string, string>> StaticAccessors = new();

    public void Add(string className, MethodDeclarationSyntax method)
    {
        var key = (className, method.Identifier.Text);
        if (!Methods.ContainsKey(key))
            Methods[key] = new List<MethodDeclarationSyntax>();
        Methods[key].Add(method);
        KnownClasses.Add(className);
    }

    public void AddMember(string className, string memberName, string typeName)
    {
        if (!MemberTypes.ContainsKey(className))
            MemberTypes[className] = new Dictionary<string, string>();
        MemberTypes[className].TryAdd(memberName, typeName);
    }

    public string? ResolveFieldType(string className, string memberName)
    {
        // 일반 필드/프로퍼티
        if (MemberTypes.TryGetValue(className, out var members) &&
            members.TryGetValue(memberName, out var t))
            return t;

        // 정적 접근자 힌트
        if (StaticAccessors.TryGetValue(className, out var accessors) &&
            accessors.TryGetValue(memberName, out var hint))
            return hint;

        return null;
    }

    public string? ResolveReturnType(string className, string methodName)
    {
        if (ReturnTypes.TryGetValue(className, out var returns) &&
            returns.TryGetValue(methodName, out var t))
            return t;
        return null;
    }
}

// ── 분석기 ───────────────────────────────────────────────────

public class MethodCallAnalyzer
{
    private MethodIndex _index = new();

    // 힌트 파일을 로드 (없으면 빈 힌트로 진행)
    public void LoadHints(string scanPath)
    {
        var candidates = new[]
        {
            Path.Combine(scanPath, ".gdep-hints.json"),
            Path.Combine(Directory.GetCurrentDirectory(), ".gdep-hints.json"),
        };

        foreach (var path in candidates)
        {
            if (!File.Exists(path)) continue;
            try
            {
                var json = File.ReadAllText(path);
                var hints = JsonSerializer.Deserialize<GdepHints>(json,
                    new JsonSerializerOptions { PropertyNameCaseInsensitive = true });

                if (hints?.StaticAccessors != null)
                {
                    foreach (var (cls, props) in hints.StaticAccessors)
                        _index.StaticAccessors[cls] = props;
                }
                Console.Error.WriteLine($"[gdep] 힌트 파일 로드: {path} ({_index.StaticAccessors.Count}개 클래스)");
                return;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[gdep] 힌트 파일 파싱 오류: {ex.Message}");
            }
        }
    }

    public void BuildIndex(IEnumerable<string> filePaths)
    {
        _index = new MethodIndex();

        // 기존 StaticAccessors 유지 (LoadHints가 먼저 호출된 경우)
        foreach (var filePath in filePaths)
        {
            string code;
            try { code = File.ReadAllText(filePath); }
            catch { continue; }

            var tree = CSharpSyntaxTree.ParseText(code);
            var root = tree.GetCompilationUnitRoot();

            var typeDecls = root.DescendantNodes()
                .Where(n => n is ClassDeclarationSyntax
                         or StructDeclarationSyntax
                         or InterfaceDeclarationSyntax);

            foreach (var typeDecl in typeDecls)
            {
                var className = typeDecl switch
                {
                    ClassDeclarationSyntax c    => c.Identifier.Text,
                    StructDeclarationSyntax s   => s.Identifier.Text,
                    InterfaceDeclarationSyntax i => i.Identifier.Text,
                    _ => null
                };
                if (className == null) continue;

                _index.KnownClasses.Add(className);

                foreach (var method in typeDecl.ChildNodes().OfType<MethodDeclarationSyntax>())
                    _index.Add(className, method);

                foreach (var field in typeDecl.ChildNodes().OfType<FieldDeclarationSyntax>())
                {
                    var typeName = ExtractSimpleType(field.Declaration.Type.ToString());
                    foreach (var v in field.Declaration.Variables)
                        _index.AddMember(className, v.Identifier.Text, typeName);
                }

                foreach (var prop in typeDecl.ChildNodes().OfType<PropertyDeclarationSyntax>())
                {
                    var typeName = ExtractSimpleType(prop.Type.ToString());
                    _index.AddMember(className, prop.Identifier.Text, typeName);
                }
            }
        }

        RebuildReturnTypes();
    }

    // 힌트 파일에서 자동 감지: StaticAccessors를 인덱스에 등록된 정적 클래스로 보완
    public void AutoDetectStaticAccessors()
    {
        foreach (var (className, members) in _index.MemberTypes)
        {
            // 이미 힌트에 있으면 스킵
            if (_index.StaticAccessors.ContainsKey(className)) continue;

            // MemberTypes 중 값이 KnownClasses에 있는 것만 정적 접근자 후보로 등록
            var resolved = members
                .Where(kv => _index.KnownClasses.Contains(kv.Value))
                .ToDictionary(kv => kv.Key, kv => kv.Value);

            if (resolved.Count > 0)
                _index.StaticAccessors.TryAdd(className, resolved);
        }
    }

    private void RebuildReturnTypes()
    {
        foreach (var ((className, methodName), methods) in _index.Methods)
        {
            foreach (var method in methods)
            {
                var returnType = ExtractSimpleType(method.ReturnType.ToString());
                if (!string.IsNullOrEmpty(returnType) && _index.KnownClasses.Contains(returnType))
                {
                    if (!_index.ReturnTypes.ContainsKey(className))
                        _index.ReturnTypes[className] = new Dictionary<string, string>();
                    _index.ReturnTypes[className].TryAdd(methodName, returnType);
                }
            }
        }
    }

    public CallGraph Trace(string entryClass, string entryMethod,
        int maxDepth, HashSet<string>? focusClasses = null)
    {
        var graph = new CallGraph();
        var visited = new HashSet<string>();

        var entryNode = MakeNode(entryClass, entryMethod);
        graph.AddNode(entryNode);

        Dfs(entryClass, entryMethod, entryNode, 0, maxDepth, visited, graph, focusClasses);
        return graph;
    }

    private void Dfs(string className, string methodName, CallNode fromNode,
        int depth, int maxDepth, HashSet<string> visited,
        CallGraph graph, HashSet<string>? focusClasses)
    {
        if (depth >= maxDepth) return;

        if (focusClasses != null && depth > 0 && !focusClasses.Contains(className))
            return;

        if (!visited.Add($"{className}.{methodName}")) return;

        var key = (className, methodName);
        if (!_index.Methods.TryGetValue(key, out var methodList)) return;

        foreach (var method in methodList)
            AnalyzeMethodBody(className, method, fromNode, depth, maxDepth, visited, graph, focusClasses);
    }

    private void AnalyzeMethodBody(string className, MethodDeclarationSyntax method,
        CallNode fromNode, int depth, int maxDepth,
        HashSet<string> visited, CallGraph graph, HashSet<string>? focusClasses)
    {
        if (method.Body == null && method.ExpressionBody == null) return;

        SyntaxNode bodyRoot = (SyntaxNode?)method.Body ?? method.ExpressionBody!;

        var invocations = bodyRoot.DescendantNodes()
            .OfType<InvocationExpressionSyntax>()
            .ToList();

        foreach (var inv in invocations)
        {
            var context = DetectContext(inv, bodyRoot);
            var (targetClass, targetMethod, isDynamic) = ResolveInvocation(inv, className);

            if (targetMethod == null) continue;
            if (IsNoisyCall(targetMethod)) continue;

            bool isLeaf = focusClasses != null
                && targetClass != null
                && !focusClasses.Contains(targetClass);

            var toNode = targetClass != null
                ? MakeNode(targetClass, targetMethod, isDynamic, isExternal: isLeaf)
                : new CallNode("?", targetMethod, IsExternal: true, IsHandlerDispatch: isDynamic);

            graph.AddNode(toNode);
            graph.AddEdge(new CallEdge(fromNode, toNode, context, isDynamic));

            if (targetClass != null && !isDynamic && !isLeaf)
                Dfs(targetClass, targetMethod, toNode, depth + 1, maxDepth, visited, graph, focusClasses);
        }
    }

    // ── 호출 해석 ─────────────────────────────────────────────

    private (string? cls, string? method, bool isDynamic) ResolveInvocation(
        InvocationExpressionSyntax inv, string currentClass)
    {
        var expr = inv.Expression;

        // 딕셔너리 핸들러 패턴
        if (expr is MemberAccessExpressionSyntax ma && ma.Name.Identifier.Text == "TryGetValue")
            return (currentClass, $"(dispatch:{ma.Expression})", true);

        // handler(...) 직접 호출
        if (expr is IdentifierNameSyntax invId &&
            (invId.Identifier.Text == "handler" ||
             invId.Identifier.Text.EndsWith("Handler") ||
             invId.Identifier.Text.EndsWith("Action")))
            return (currentClass, $"(invoke:{invId.Identifier.Text})", true);

        if (expr is MemberAccessExpressionSyntax memberAccess)
        {
            var methodName = memberAccess.Name.Identifier.Text;
            var receiver   = memberAccess.Expression;
            var resolved   = ResolveReceiver(receiver, currentClass, inv);
            return (resolved, methodName, false);
        }

        if (expr is IdentifierNameSyntax simpleId)
            return (currentClass, simpleId.Identifier.Text, false);

        if (expr is ConditionalAccessExpressionSyntax condAccess)
        {
            if (condAccess.WhenNotNull is InvocationExpressionSyntax innerInv)
            {
                // 케이스 1: obj?.Method()
                if (innerInv.Expression is MemberBindingExpressionSyntax binding)
                {
                    var baseType = ResolveReceiver(condAccess.Expression, currentClass, inv);
                    return (baseType, binding.Name.Identifier.Text, false);
                }

                // 케이스 2: obj?.Prop.Method()
                if (innerInv.Expression is MemberAccessExpressionSyntax chainedAccess)
                {
                    var methodName = chainedAccess.Name.Identifier.Text;
                    var baseType = ResolveReceiver(condAccess.Expression, currentClass, inv);
                    if (baseType != null && chainedAccess.Expression is MemberBindingExpressionSyntax propBinding)
                    {
                        var propName = propBinding.Name.Identifier.Text;
                        var propType = _index.ResolveFieldType(baseType, propName);
                        if (propType != null)
                            return (propType, methodName, false);
                    }
                    return (baseType, methodName, false);
                }
            }
        }

        return (null, null, false);
    }

    private string? ResolveReceiver(ExpressionSyntax receiver, string currentClass,
        InvocationExpressionSyntax? context = null)
    {
        switch (receiver)
        {
            case ThisExpressionSyntax:
            case BaseExpressionSyntax:
                return currentClass;

            case IdentifierNameSyntax id:
            {
                var name = id.Identifier.Text;
                var fieldType = _index.ResolveFieldType(currentClass, name);
                if (fieldType != null && _index.KnownClasses.Contains(fieldType))
                    return fieldType;
                if (_index.KnownClasses.Contains(name)) return name;

                // 정적 접근자 힌트에서 클래스명 자체 확인 (Managers 자체는 클래스)
                if (_index.StaticAccessors.ContainsKey(name)) return name;

                return null;
            }

            // ★ 핵심 수정: Managers.UI.ShowPopup() 에서 Managers.UI 처리
            case MemberAccessExpressionSyntax chainedAccess:
            {
                var propName = chainedAccess.Name.Identifier.Text;
                var baseType = ResolveReceiver(chainedAccess.Expression, currentClass);
                if (baseType == null) return null;

                // baseType의 propName 프로퍼티 타입 조회
                var propType = _index.ResolveFieldType(baseType, propName);
                if (propType != null && _index.KnownClasses.Contains(propType))
                    return propType;

                // propType이 KnownClasses에 없어도 힌트에서 직접 매핑 가능
                if (propType != null) return propType;

                return null;
            }

            // 메서드 반환 타입으로 해석
            case InvocationExpressionSyntax innerInv:
            {
                var (innerCls, innerMethod, _) = ResolveInvocation(innerInv, currentClass);
                if (innerCls != null && innerMethod != null)
                {
                    var returnType = _index.ResolveReturnType(innerCls, innerMethod);
                    if (returnType != null) return returnType;
                }
                return null;
            }

            case ConditionalAccessExpressionSyntax cond:
                return ResolveReceiver(cond.Expression, currentClass);

            case ParenthesizedExpressionSyntax paren:
                return ResolveReceiver(paren.Expression, currentClass);

            case CastExpressionSyntax cast:
            {
                var typeName = ExtractSimpleType(cast.Type.ToString());
                return _index.KnownClasses.Contains(typeName) ? typeName : null;
            }

            // obj?.Prop.Method() 에서 Prop 부분이 MemberBindingExpression으로 파싱됨
            // 상위 ConditionalAccessExpression을 찾아서 base 타입 → Prop 타입 순으로 해석
            case MemberBindingExpressionSyntax memberBinding:
            {
                var propName = memberBinding.Name.Identifier.Text;
                // 상위 ConditionalAccessExpression 탐색
                var condAccess = receiver.Ancestors()
                    .OfType<ConditionalAccessExpressionSyntax>()
                    .FirstOrDefault();
                if (condAccess == null) return null;

                var baseType = ResolveReceiver(condAccess.Expression, currentClass);
                if (baseType == null) return null;

                var propType = _index.ResolveFieldType(baseType, propName);
                return propType ?? null;
            }

            default:
                return null;
        }
    }

    // ── 컨텍스트 감지 ─────────────────────────────────────────

    private string? DetectContext(InvocationExpressionSyntax inv, SyntaxNode bodyRoot)
    {
        var ancestors = inv.Ancestors();
        if (ancestors.OfType<LockStatementSyntax>().Any()) return "lock";
        if (ancestors.OfType<AnonymousFunctionExpressionSyntax>().Any())
        {
            var outerInv = ancestors.OfType<InvocationExpressionSyntax>().FirstOrDefault();
            if (outerInv?.Expression.ToString().Contains("ThreadPool") == true ||
                outerInv?.Expression.ToString().Contains("Task.Run") == true)
                return "thread";
            return "lambda";
        }
        if (ancestors.OfType<AwaitExpressionSyntax>().Any()) return "await";
        return null;
    }

    // ── 유틸 ──────────────────────────────────────────────────

    public IReadOnlyDictionary<string, Dictionary<string, string>> GetStaticAccessors()
        => _index.StaticAccessors;

    public IReadOnlySet<string> GetKnownClasses() => _index.KnownClasses;

    private CallNode MakeNode(string className, string methodName,
        bool isDynamic = false, bool isExternal = false)
    {
        var key = (className, methodName);
        var isAsync = _index.Methods.TryGetValue(key, out var methods) &&
                      methods.Any(m => m.Modifiers.Any(mod => mod.Text == "async"));
        var isKnown = _index.KnownClasses.Contains(className) ||
                      _index.StaticAccessors.ContainsKey(className);

        return new CallNode(className, methodName,
            IsAsync: isAsync,
            IsExternal: isExternal || !isKnown,
            IsHandlerDispatch: isDynamic);
    }

    private string ExtractSimpleType(string typeName)
    {
        typeName = typeName.Trim().TrimEnd('?');

        // 제네릭 처리: Dictionary<K,V> → V, List<T> → T
        // 단순히 '<' 뒤를 자르면 "K,V" 같은 복합 타입이 남음
        if (typeName.Contains('<'))
        {
            var start = typeName.IndexOf('<') + 1;
            var inner = typeName.Substring(start).TrimEnd('>').Trim();

            // 중첩 제네릭이 있으면 가장 마지막 단순 타입만 추출
            // Dictionary<ETB_CARD_TYPE, List<InGameShopProduct>> → InGameShopProduct
            var depth = 0;
            var lastSegmentStart = 0;
            for (int i = 0; i < inner.Length; i++)
            {
                if (inner[i] == '<') depth++;
                else if (inner[i] == '>') depth--;
                else if (inner[i] == ',' && depth == 0)
                    lastSegmentStart = i + 1;
            }
            typeName = inner.Substring(lastSegmentStart).Trim().TrimEnd('>').Trim();

            // 남은 제네릭 재귀 처리
            if (typeName.Contains('<'))
                typeName = ExtractSimpleType(typeName);
        }

        // 네임스페이스 제거
        return typeName.Split('.').Last().Trim().TrimEnd('?');
    }

    private static readonly HashSet<string> NoisyCalls = new()
    {
        // 컬렉션 기본 연산
        "Add", "Remove", "Clear", "Count", "Contains", "ContainsKey", "ContainsValue",
        "Any", "Where", "Select", "ToList", "ToArray", "ToDictionary", "ToHashSet",
        "First", "FirstOrDefault", "Last", "LastOrDefault",
        "Single", "SingleOrDefault", "Skip", "Take",
        "OrderBy", "OrderByDescending", "GroupBy", "Distinct", "Zip",
        "TryAdd", "TryGetValue", "TryRemove",
        "AddRange", "InsertRange", "RemoveAll", "RemoveRange",
        "Keys", "Values", "Entries",
        // 기본 타입 연산
        "ToString", "GetHashCode", "Equals", "GetType", "GetLength",
        "Parse", "TryParse", "Format", "Concat", "Join", "Split", "Trim",
        "IsNullOrEmpty", "IsNullOrWhiteSpace",
        // 로그
        "Log", "LogWarning", "LogError", "LogException",
        // Unity 내장 - 컴포넌트/오브젝트
        "GetComponent", "GetComponentInChildren", "GetComponentInParent",
        "FindObjectOfType", "FindObjectsOfType",
        "Instantiate", "Destroy", "DestroyImmediate",
        "SetActive",          // gameObject.SetActive()
        "DontDestroyOnLoad",
        // Unity 내장 - 코루틴/비동기
        "StartCoroutine", "StopCoroutine", "StopAllCoroutines",
        "WaitForSeconds", "WaitForEndOfFrame", "WaitUntil", "WaitWhile",
        "WhenAll", "WhenAny", "Delay",
        "Forget", "GetAwaiter", "GetResult", "ConfigureAwait",
        "RunOnThreadPool",    // UniTask.RunOnThreadPool()
        "RunOnMainThread",
        // PlayerPrefs / Unity 정적 유틸
        "GetInt", "GetFloat", "GetString",   // PlayerPrefs
        "SetInt", "SetFloat", "SetString",
        "HasKey", "DeleteKey", "DeleteAll", "Save",
        // Invoke / 이벤트
        "Invoke", "InvokeRepeating", "CancelInvoke",
    };

    private bool IsNoisyCall(string methodName) =>
        NoisyCalls.Contains(methodName) ||
        methodName.StartsWith("get_") || methodName.StartsWith("set_") ||
        methodName.StartsWith("op_") || methodName.StartsWith("add_") ||
        methodName.StartsWith("remove_");
}