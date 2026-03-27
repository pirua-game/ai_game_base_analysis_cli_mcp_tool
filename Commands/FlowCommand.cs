using System.Text.Json;
using System.Text.Json.Serialization;
using Spectre.Console;
using gdep.Parser;

namespace gdep.Commands;

// ── JSON 직렬화 모델 ──────────────────────────────────────────

public record FlowNodeJson(
    [property: JsonPropertyName("id")]         string Id,
    [property: JsonPropertyName("class")]      string Class,
    [property: JsonPropertyName("method")]     string Method,
    [property: JsonPropertyName("label")]      string Label,      // 표시용 레이블
    [property: JsonPropertyName("isAsync")]    bool IsAsync,
    [property: JsonPropertyName("isEntry")]    bool IsEntry,
    [property: JsonPropertyName("isDispatch")] bool IsDispatch,
    [property: JsonPropertyName("isLeaf")]     bool IsLeaf
);

public record FlowEdgeJson(
    [property: JsonPropertyName("from")]      string From,
    [property: JsonPropertyName("to")]        string To,
    [property: JsonPropertyName("context")]   string? Context,
    [property: JsonPropertyName("isDynamic")] bool IsDynamic,
    [property: JsonPropertyName("condition")] string? Condition
);

public record FlowDispatchJson(
    [property: JsonPropertyName("from")]    string From,
    [property: JsonPropertyName("handler")] string Handler
);

public record SwitchDispatchJson(
    [property: JsonPropertyName("switchExpression")] string SwitchExpression,
    [property: JsonPropertyName("fromMethod")]       string FromMethod,
    [property: JsonPropertyName("caseTargets")]      List<string> CaseTargets
);

public record FlowGraphJson(
    [property: JsonPropertyName("entry")]            string Entry,
    [property: JsonPropertyName("entryClass")]       string EntryClass,
    [property: JsonPropertyName("depth")]            int Depth,
    [property: JsonPropertyName("focus")]            string[] Focus,
    [property: JsonPropertyName("nodes")]            List<FlowNodeJson> Nodes,
    [property: JsonPropertyName("edges")]            List<FlowEdgeJson> Edges,
    [property: JsonPropertyName("dispatches")]       List<FlowDispatchJson> Dispatches,
    [property: JsonPropertyName("switchDispatches")] List<SwitchDispatchJson> SwitchDispatches
);

public class FlowCommand
{
    private readonly MethodCallAnalyzer _analyzer = new();

    public void Execute(string path, string className, string methodName,
        int maxDepth = 4, string format = "console", string? outputFile = null,
        bool skipProto = true, string[]? ignorePatterns = null,
        string[]? focusClasses = null)
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            return;
        }

        var csFiles = ScanCommand.CollectFiles(path, skipProto, ignorePatterns);

        _analyzer.LoadHints(path);

        AnsiConsole.Progress().Start(ctx =>
        {
            var t1 = ctx.AddTask("[teal]Building method index...[/]", maxValue: 1);
            _analyzer.BuildIndex(csFiles);
            _analyzer.AutoDetectStaticAccessors();
            t1.Value = 1;
        });

        HashSet<string>? focusSet = null;
        if (focusClasses != null && focusClasses.Length > 0)
        {
            focusSet = new HashSet<string>(focusClasses, StringComparer.OrdinalIgnoreCase);
            focusSet.Add(className);
        }

        CallGraph graph = new();
        AnsiConsole.Progress().Start(ctx =>
        {
            var t2 = ctx.AddTask("[teal]Tracing call flow...[/]", maxValue: 1);
            graph = _analyzer.Trace(className, methodName, maxDepth, focusSet);
            t2.Value = 1;
        });

        if (!graph.Nodes.Any())
        {
            AnsiConsole.MarkupLine($"[red]Method not found: {className}.{methodName}[/]");
            return;
        }

        AnsiConsole.WriteLine();

        if (format.ToLower() == "json")
        {
            var json = BuildJson(graph, className, methodName, maxDepth,
                focusSet?.ToArray() ?? Array.Empty<string>());
            OutputContent(json, outputFile, ".json");
            if (string.IsNullOrEmpty(outputFile))
                return;

            PrintStats(graph, focusSet);
            AnsiConsole.MarkupLine($"[green]Saved to:[/] {outputFile}");
            return;
        }

        PrintStats(graph, focusSet);

        var content = format.ToLower() switch
        {
            "mermaid" => ExportMermaid(graph, className),
            "dot"     => ExportDot(graph, className, methodName),
            _         => null
        };

        if (content != null)
        {
            OutputContent(content, outputFile, format == "dot" ? ".dot" : ".md");
            if (!string.IsNullOrEmpty(outputFile))
                AnsiConsole.MarkupLine($"[green]Saved to:[/] {outputFile}");
        }
        else
        {
            PrintConsole(graph, className, methodName, maxDepth);
        }
    }

    // ── Node Label Calculation ─────────────────────────────────────

    private string GetNodeLabel(CallNode node, string entryClass)
    {
        if (node.IsHandlerDispatch)
        {
            var handler = node.MethodName
                .Replace("(dispatch:", "").Replace("(invoke:", "").TrimEnd(')');
            return $"⇢ {handler}";
        }
        if (node.ClassName == "?" || node.ClassName == "_")
            return $"? {node.MethodName}";

        // Same class: method name only, Other class: ClassName.method
        return node.ClassName.Equals(entryClass, StringComparison.OrdinalIgnoreCase)
            ? node.MethodName
            : $"{node.ClassName}.{node.MethodName}";
    }

    // ── JSON Build ─────────────────────────────────────────────

    private string BuildJson(CallGraph graph, string entryClass, string entryMethod,
        int depth, string[] focus)
    {
        var entryId = $"{entryClass}.{entryMethod}".Replace('<','_').Replace('>','_');

        var nodes = graph.Nodes.Select(n => new FlowNodeJson(
            Id:         n.Id,
            Class:      n.ClassName,
            Method:     n.MethodName,
            Label:      GetNodeLabel(n, entryClass),
            IsAsync:    n.IsAsync,
            IsEntry:    n.Id == entryId,
            IsDispatch: n.IsHandlerDispatch,
            IsLeaf:     n.IsExternal
        )).ToList();

        var seen = new HashSet<string>();
        var edges = new List<FlowEdgeJson>();
        foreach (var e in graph.Edges)
        {
            var key = $"{e.From.Id}->{e.To.Id}";
            if (!seen.Add(key)) continue;
            edges.Add(new FlowEdgeJson(
                From:      e.From.Id,
                To:        e.To.Id,
                Context:   e.Note,
                IsDynamic: e.IsDynamic,
                Condition: e.Condition
            ));
        }

        var dispatches = graph.Nodes
            .Where(n => n.IsHandlerDispatch)
            .Select(n =>
            {
                var caller = graph.Edges
                    .Where(e => e.To.Id == n.Id && e.IsDynamic)
                    .Select(e => e.From.Id)
                    .FirstOrDefault() ?? "";
                var handler = n.MethodName
                    .Replace("(dispatch:", "").Replace("(invoke:", "").TrimEnd(')');
                return new FlowDispatchJson(From: caller, Handler: handler);
            })
            .ToList();

        // Group switch-case edges: edges with "switch: X" condition from same source
        var switchDispatches = edges
            .Where(e => e.Condition != null && e.Condition.StartsWith("switch: "))
            .GroupBy(e => (From: e.From, Expr: e.Condition!))
            .Select(g => new SwitchDispatchJson(
                SwitchExpression: g.Key.Expr["switch: ".Length..],
                FromMethod:       g.Key.From,
                CaseTargets:      g.Select(e => e.To).Distinct().ToList()
            ))
            .Where(sd => sd.CaseTargets.Count > 1)
            .ToList();

        var result = new FlowGraphJson(
            Entry:            $"{entryClass}.{entryMethod}",
            EntryClass:       entryClass,
            Depth:            depth,
            Focus:            focus,
            Nodes:            nodes,
            Edges:            edges,
            Dispatches:       dispatches,
            SwitchDispatches: switchDispatches
        );

        return JsonSerializer.Serialize(result, new JsonSerializerOptions
        {
            WriteIndented = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        });
    }

    private void OutputContent(string content, string? outputFile, string defaultExt)
    {
        if (!string.IsNullOrEmpty(outputFile))
        {
            if (!Path.HasExtension(outputFile))
                outputFile += defaultExt;
            File.WriteAllText(outputFile, content);
        }
        else
        {
            Console.WriteLine(content);
        }
    }

    private void PrintStats(CallGraph graph, HashSet<string>? focusSet)
    {
        var focusInfo = focusSet != null
            ? $" · Focus: {string.Join(", ", focusSet)}"
            : "";
        AnsiConsole.MarkupLine(
            $"[gray]Nodes [white]{graph.Nodes.Count}[/] · Edges [white]{graph.Edges.Count}[/]" +
            $"{Markup.Escape(focusInfo)}[/]");

        var dynamicCount  = graph.Nodes.Count(n => n.IsHandlerDispatch);
        var externalCount = graph.Nodes.Count(n => n.IsExternal && n.ClassName != "?");
        var unknownCount  = graph.Nodes.Count(n => n.ClassName == "?");

        if (dynamicCount > 0 || externalCount > 0 || unknownCount > 0)
            AnsiConsole.MarkupLine(
                $"[gray]Dynamic dispatch [yellow]{dynamicCount}[/] · " +
                $"Leaf nodes [gray]{externalCount}[/] · " +
                $"Unresolved receivers [red]{unknownCount}[/][/]");

        AnsiConsole.WriteLine();
    }

    // ── Console Tree Output ───────────────────────────────────────

    private void PrintConsole(CallGraph graph, string entryClass, string entryMethod, int maxDepth)
    {
        Console.WriteLine("Legend: async  lock  thread  ⇢ dispatch  ○ leaf  ? unresolved");
        AnsiConsole.WriteLine();

        var adjMap = graph.Edges
            .GroupBy(e => e.From.Id)
            .ToDictionary(g => g.Key, g => g.ToList());

        PrintTree(graph.Nodes.First(), adjMap, new HashSet<string>(), "", true, entryClass);
        AnsiConsole.WriteLine();

        var dispatches = graph.Nodes.Where(n => n.IsHandlerDispatch).ToList();
        if (dispatches.Any())
        {
            AnsiConsole.MarkupLine("[yellow]── Dynamic Dispatch Points[/]");
            foreach (var d in dispatches)
                AnsiConsole.MarkupLine($"  [yellow]⇢[/] {Markup.Escape(GetNodeLabel(d, entryClass))}");
        }

        var unknown = graph.Nodes.Where(n => n.ClassName == "?").ToList();
        if (unknown.Any())
        {
            AnsiConsole.WriteLine();
            AnsiConsole.MarkupLine($"[red]── Unresolved Receivers: {unknown.Count}[/]");
            foreach (var u in unknown.Take(8))
                AnsiConsole.MarkupLine($"  [red]?[/] {Markup.Escape(u.MethodName)}");
            if (unknown.Count > 8)
                AnsiConsole.MarkupLine($"  [gray]... and {unknown.Count - 8} more[/]");
        }
    }

    private void PrintTree(CallNode node, Dictionary<string, List<CallEdge>> adj,
        HashSet<string> visited, string prefix, bool isLast, string entryClass)
    {
        var connector = isLast ? "└── " : "├── ";
        AnsiConsole.MarkupLine($"{prefix}{connector}{FormatNodeLabel(node, entryClass)}");

        if (node.IsExternal || node.IsHandlerDispatch) return;
        if (visited.Contains(node.Id))
        {
            AnsiConsole.MarkupLine($"{prefix + (isLast ? "    " : "│   ")}[gray](↩ repeat)[/]");
            return;
        }
        visited.Add(node.Id);

        if (!adj.TryGetValue(node.Id, out var edges)) return;
        var childPrefix = prefix + (isLast ? "    " : "│   ");
        var uniqueEdges = edges.GroupBy(e => e.To.Id).Select(g => g.First()).ToList();

        for (int i = 0; i < uniqueEdges.Count; i++)
        {
            var edge        = uniqueEdges[i];
            var isLastChild = i == uniqueEdges.Count - 1;

            if (edge.Note is "lock" or "thread" or "lambda")
            {
                var (noteColor, noteLabel) = edge.Note switch
                {
                    "lock"   => ("red",    "lock"),
                    "thread" => ("purple", "thread"),
                    _        => ("blue",   "lambda")
                };
                AnsiConsole.MarkupLine(
                    $"{childPrefix}{(isLastChild ? "└" : "├")}─ [{noteColor}]{noteLabel}[/]");
                PrintTree(edge.To, adj, visited,
                    childPrefix + (isLastChild ? "    " : "│   "), true, entryClass);
            }
            else
            {
                PrintTree(edge.To, adj, visited, childPrefix, isLastChild, entryClass);
            }
        }
    }

    private string FormatNodeLabel(CallNode node, string entryClass)
    {
        if (node.IsHandlerDispatch) return $"[yellow]⇢ {Markup.Escape(GetNodeLabel(node, entryClass))}[/]";
        if (node.ClassName == "?")  return $"[red]? {Markup.Escape(node.MethodName)}[/]";
        if (node.IsExternal)        return $"[gray]○ {Markup.Escape(GetNodeLabel(node, entryClass))}[/]";

        // Same class: method name only (White)
        // Other class: ClassName.method (Class gray, Method teal)
        if (node.ClassName.Equals(entryClass, StringComparison.OrdinalIgnoreCase))
        {
            var label = $"[teal]{Markup.Escape(node.MethodName)}[/]";
            if (node.IsAsync) label += " [blue]async[/]";
            return label;
        }
        else
        {
            var label = $"[gray]{Markup.Escape(node.ClassName)}[/].[teal]{Markup.Escape(node.MethodName)}[/]";
            if (node.IsAsync) label += " [blue]async[/]";
            return label;
        }
    }

    // ── Mermaid Output ─────────────────────────────────────────

    private string ExportMermaid(CallGraph graph, string entryClass)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("flowchart TD");
        sb.AppendLine();

        var unknownNodes = graph.Nodes.Where(n => n.ClassName == "?").ToList();
        var byClass = graph.Nodes
            .Where(n => n.ClassName != "?")
            .GroupBy(n => n.ClassName)
            .OrderBy(g => g.Key);

        foreach (var group in byClass)
        {
            sb.AppendLine($"  subgraph {SafeId(group.Key)}[\"{EscMermaid(group.Key)}\"]");
            foreach (var node in group)
            {
                var safe  = SafeId(node.Id);
                // Label: method name if same class, Class.method otherwise
                var displayLabel = GetNodeLabel(node, entryClass);
                var shape = node.IsHandlerDispatch
                    ? $"{safe}{{{{\"⇢ {EscMermaid(node.MethodName)}\"}}}}"
                    : node.IsExternal ? $"{safe}([\"○ {EscMermaid(displayLabel)}\"])"
                    : node.IsAsync    ? $"{safe}[\"/\"{EscMermaid(displayLabel)}\"/\"]"
                    : $"{safe}[\"{EscMermaid(displayLabel)}\"]";
                sb.AppendLine($"    {shape}");
            }
            sb.AppendLine("  end");
            sb.AppendLine();
        }

        if (unknownNodes.Any())
        {
            sb.AppendLine("  subgraph Unknown[\"Unresolved Receiver\"]");
            foreach (var n in unknownNodes)
                sb.AppendLine($"    {SafeId(n.Id)}([\"? {EscMermaid(n.MethodName)}\"])");
            sb.AppendLine("  end");
            sb.AppendLine();
        }

        var seen = new HashSet<string>();
        foreach (var edge in graph.Edges)
        {
            var key = $"{edge.From.Id}->{edge.To.Id}";
            if (!seen.Add(key)) continue;
            var arrow = edge.IsDynamic        ? "-.->|dispatch|"
                      : edge.Note == "thread" ? "==>|thread|"
                      : edge.Note == "lock"   ? "-->|lock|"
                      : edge.Note == "lambda" ? "-.->|lambda|"
                      : "-->";
            sb.AppendLine($"  {SafeId(edge.From.Id)} {arrow} {SafeId(edge.To.Id)}");
        }

        sb.AppendLine();
        sb.AppendLine("  classDef async    fill:#E6F1FB,stroke:#185FA5,color:#0C447C");
        sb.AppendLine("  classDef dispatch fill:#FAEEDA,stroke:#BA7517,color:#633806");
        sb.AppendLine("  classDef leaf     fill:#F1EFE8,stroke:#888780,color:#5F5E5A");
        sb.AppendLine("  classDef entry    fill:#E1F5EE,stroke:#0F6E56,color:#085041,font-weight:bold");
        sb.AppendLine("  classDef unknown  fill:#FCEBEB,stroke:#A32D2D,color:#791F1F,stroke-dasharray:3");

        var entry = graph.Nodes.FirstOrDefault();
        if (entry != null) sb.AppendLine($"  class {SafeId(entry.Id)} entry");
        foreach (var n in graph.Nodes.Where(v => v.IsAsync && !v.IsHandlerDispatch))
            sb.AppendLine($"  class {SafeId(n.Id)} async");
        foreach (var n in graph.Nodes.Where(v => v.IsHandlerDispatch))
            sb.AppendLine($"  class {SafeId(n.Id)} dispatch");
        foreach (var n in graph.Nodes.Where(v => v.IsExternal && v.ClassName != "?"))
            sb.AppendLine($"  class {SafeId(n.Id)} leaf");
        foreach (var n in unknownNodes)
            sb.AppendLine($"  class {SafeId(n.Id)} unknown");

        return sb.ToString();
    }

    // ── DOT Output ─────────────────────────────────────────────

    private string ExportDot(CallGraph graph, string entryClass, string entryMethod)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine($"digraph flow_{SafeId(entryClass + "_" + entryMethod)} {{");
        sb.AppendLine("  rankdir=TB;");
        sb.AppendLine("  node [shape=box, style=filled, fontname=\"sans-serif\", fontsize=11];");
        sb.AppendLine("  edge [fontname=\"sans-serif\", fontsize=9];");
        sb.AppendLine();

        var unknownNodes = graph.Nodes.Where(n => n.ClassName == "?").ToList();
        if (unknownNodes.Any())
        {
            sb.AppendLine("  subgraph cluster_Unknown {");
            sb.AppendLine("    label=\"Unresolved Receiver\"; style=dashed; color=\"#A32D2D\";");
            foreach (var n in unknownNodes)
                sb.AppendLine($"    \"{EscDot(n.Id)}\" [label=\"? {EscDot(n.MethodName)}\", " +
                    "fillcolor=\"#FCEBEB\", color=\"#A32D2D\", fontcolor=\"#791F1F\"];");
            sb.AppendLine("  }");
            sb.AppendLine();
        }

        foreach (var group in graph.Nodes.Where(n => n.ClassName != "?").GroupBy(n => n.ClassName))
        {
            sb.AppendLine($"  subgraph cluster_{SafeId(group.Key)} {{");
            sb.AppendLine($"    label=\"{EscDot(group.Key)}\"; style=dashed; color=\"#B4B2A9\";");
            foreach (var n in group)
            {
                var color = n.IsHandlerDispatch
                    ? "fillcolor=\"#FAEEDA\", color=\"#BA7517\", fontcolor=\"#633806\""
                    : n.IsExternal ? "fillcolor=\"#F1EFE8\", color=\"#888780\", fontcolor=\"#5F5E5A\""
                    : n.IsAsync    ? "fillcolor=\"#E6F1FB\", color=\"#185FA5\", fontcolor=\"#0C447C\""
                    : "fillcolor=\"#E1F5EE\", color=\"#0F6E56\", fontcolor=\"#085041\"";
                // Apply label in DOT too
                var displayLabel = GetNodeLabel(n, entryClass);
                var pfx = n.IsHandlerDispatch ? "⇢ " : n.IsAsync ? "⏱ " : "";
                sb.AppendLine($"    \"{EscDot(n.Id)}\" [label=\"{pfx}{EscDot(displayLabel)}\", {color}];");
            }
            sb.AppendLine("  }");
            sb.AppendLine();
        }

        var seen = new HashSet<string>();
        foreach (var edge in graph.Edges)
        {
            var key = $"{edge.From.Id}->{edge.To.Id}";
            if (!seen.Add(key)) continue;
            var style = edge.IsDynamic        ? "style=dashed, color=\"#BA7517\""
                      : edge.Note == "thread" ? "style=bold, color=\"#534AB7\""
                      : edge.Note == "lock"   ? "color=\"#E24B4A\""
                      : edge.Note == "lambda" ? "style=dashed, color=\"#7F77DD\""
                      : "color=\"#1D9E75\"";
            var label = edge.Note is "thread" or "lock" or "lambda" ? $", label=\"{edge.Note}\"" : "";
            sb.AppendLine($"  \"{EscDot(edge.From.Id)}\" -> \"{EscDot(edge.To.Id)}\" [{style}{label}];");
        }
        sb.AppendLine("}");
        return sb.ToString();
    }

    private string SafeId(string s) =>
        System.Text.RegularExpressions.Regex.Replace(s, @"[^a-zA-Z0-9_]", "_");
    private string EscMermaid(string s) =>
        s.Replace("\"", "'").Replace("[", "(").Replace("]", ")")
         .Replace("{", "(").Replace("}", ")").Replace("<", "(").Replace(">", ")");
    private string EscDot(string s) => s.Replace("\"", "'").Replace("\\", "/");
}