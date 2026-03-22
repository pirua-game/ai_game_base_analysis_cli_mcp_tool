using Spectre.Console;
using gdep.Graph;
using gdep.Parser;

namespace gdep.Commands;

public class ScanCommand
{
    private readonly CSharpParser _parser = new();

    public void Execute(string path, bool showCycles, int top, bool skipProto = true,
        string[]? ignorePatterns = null, string? namespaceFilter = null, bool showNamespaces = false,
        bool showDeadCode = false, bool deep = false, string format = "console")
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            return;
        }

        var graph = new DependencyGraph();
        var csFiles = CollectFiles(path, skipProto, ignorePatterns);

        AnsiConsole.Progress()
            .Start(ctx =>
            {
                var task = ctx.AddTask("[teal]Scanning...[/]", maxValue: 1);
                var parsed = _parser.ParseFiles(csFiles, deep);

                // Apply namespace filter
                if (!string.IsNullOrEmpty(namespaceFilter))
                    parsed = parsed.Where(p =>
                        p.Node.Namespace.Contains(namespaceFilter, StringComparison.OrdinalIgnoreCase)).ToList();

                foreach (var p in parsed)
                {
                    graph.AddNode(p.Node);
                    foreach (var edge in p.Edges)
                        graph.AddEdge(p.Node.Name, edge.To, edge.Kind, edge.MemberName);
                }
                task.Value = 1;
            });

        if (skipProto)
            graph.RemoveProtoNodes();

        if (format == "json")
        {
            PrintJson(graph, csFiles.Length, path);
            return;
        }

        AnsiConsole.WriteLine();
        PrintSummary(graph, csFiles.Length, path);
        PrintCouplingRank(graph, top);

        if (showNamespaces)
            PrintNamespaceSummary(graph);

        if (showCycles)
            PrintCycles(graph);

        if (showDeadCode)
            PrintDeadCode(graph);
    }

    private void PrintJson(DependencyGraph graph, int fileCount, string path)
    {
        var allEdges = graph.Edges.Values.SelectMany(e => e).ToList();
        var deadNodes = graph.GetDeadNodes();
        
        var scores = graph.GetCouplingScores();
        var coupling = scores
            .OrderByDescending(kv => kv.Value)
            .Select(kv => new {
                name = kv.Key,
                score = kv.Value,
                ns = graph.Nodes.TryGetValue(kv.Key, out var node) ? node.Namespace : "",
                file = graph.Nodes.TryGetValue(kv.Key, out var n) ? Path.GetFileName(n.FilePath) : ""
            })
            .ToList();

        var result = new
        {
            summary = new {
                path = Path.GetFullPath(path),
                fileCount = fileCount,
                classCount = graph.Nodes.Count,
                refCount = allEdges.Count,
                deadCount = deadNodes.Count
            },
            coupling = coupling,
            deadNodes = deadNodes.Select(name => new {
                name = name,
                ns = graph.Nodes[name].Namespace,
                file = Path.GetFileName(graph.Nodes[name].FilePath),
                fullPath = graph.Nodes[name].FilePath
            }),
            cycles = graph.FindCyclesDeduped().Select(c => c.Select(n => n.node).ToList())
        };

        Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(result, new System.Text.Json.JsonSerializerOptions {
            WriteIndented = true,
            Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping
        }));
    }

    // 외부에서 그래프만 얻고 싶을 때 (DiffCommand에서 사용)
    public DependencyGraph BuildGraph(string path, bool skipProto = true,
        string[]? ignorePatterns = null, string? namespaceFilter = null, bool deep = false)
    {
        var graph = new DependencyGraph();
        if (!Directory.Exists(path)) return graph;

        var csFiles = CollectFiles(path, skipProto, ignorePatterns);
        var parsed = _parser.ParseFiles(csFiles, deep);

        if (!string.IsNullOrEmpty(namespaceFilter))
            parsed = parsed.Where(p =>
                p.Node.Namespace.Contains(namespaceFilter, StringComparison.OrdinalIgnoreCase)).ToList();

        foreach (var p in parsed)
        {
            graph.AddNode(p.Node);
            foreach (var edge in p.Edges)
                graph.AddEdge(p.Node.Name, edge.To, edge.Kind, edge.MemberName);
        }

        if (skipProto)
            graph.RemoveProtoNodes();

        return graph;
    }

    public static string[] CollectFiles(string path, bool skipProto, string[]? ignorePatterns)
    {
        var files = Directory.GetFiles(path, "*.cs", SearchOption.AllDirectories);

        if (skipProto)
            files = files.Where(f => !Path.GetFileName(f).EndsWith("_PROTO.cs")).ToArray();

        if (ignorePatterns != null && ignorePatterns.Length > 0)
            files = files.Where(f => !MatchesAnyPattern(f, ignorePatterns)).ToArray();

        return files;
    }

    // 간단한 글로브 패턴 매칭 (* = 같은 디렉토리 내, ** = 하위 포함)
    private static bool MatchesAnyPattern(string filePath, string[] patterns)
    {
        var normalized = filePath.Replace('\\', '/');
        foreach (var pattern in patterns)
        {
            var p = pattern.Replace('\\', '/').Trim();
            if (p.Contains("**"))
            {
                var part = p.Replace("**/", "").Replace("/**", "");
                if (normalized.Contains(part, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            else if (p.StartsWith("*"))
            {
                if (normalized.EndsWith(p.TrimStart('*'), StringComparison.OrdinalIgnoreCase))
                    return true;
            }
            else
            {
                if (normalized.Contains(p, StringComparison.OrdinalIgnoreCase))
                    return true;
            }
        }
        return false;
    }

    private void PrintSummary(DependencyGraph graph, int fileCount, string path)
    {
        var allEdges = graph.Edges.Values.SelectMany(e => e).ToList();
        var fieldCount = allEdges.Count(e => e.Kind == EdgeKind.Field || e.Kind == EdgeKind.Property);
        var inheritCount = allEdges.Count(e => e.Kind == EdgeKind.Inheritance);
        var deadCount = graph.GetDeadNodes().Count;

        var rootDir = Path.GetFullPath(path);
        var panel = new Panel(
            $"[white]Path[/] {rootDir}\n" +
            $"[white]Files[/] {fileCount}  |  " +
            $"[white]Classes[/] {graph.Nodes.Count}  |  " +
            $"[white]References[/] {allEdges.Count}\n" +
            $"([gray]Fields/Props {fieldCount} · Inheritance {inheritCount}[/])  |  " +
            $"[white]Orphan Nodes[/] [yellow]{deadCount}[/]")
        {
            Header = new PanelHeader("[teal] gdep scan results [/]"),
            Border = BoxBorder.Rounded
        };
        AnsiConsole.Write(panel);
        AnsiConsole.WriteLine();
    }

    private void PrintDeadCode(DependencyGraph graph)
    {
        var deadNodes = graph.GetDeadNodes();
        AnsiConsole.MarkupLine("[yellow]── [[Dead Code]] Classes with no references (Ref Count 0)[/]");

        if (!deadNodes.Any())
        {
            AnsiConsole.MarkupLine("[green]No orphan nodes found[/]\n");
            return;
        }

        var table = new Table()
            .Border(TableBorder.Simple)
            .AddColumn("Class")
            .AddColumn("Namespace")
            .AddColumn("File Path");

        foreach (var name in deadNodes)
        {
            var node = graph.Nodes[name];
            table.AddRow(
                Markup.Escape(name),
                Markup.Escape(node.Namespace),
                $"[gray]{Markup.Escape(node.FilePath)}[/]");
        }

        AnsiConsole.Write(table);
        AnsiConsole.WriteLine();
    }

    private void PrintCouplingRank(DependencyGraph graph, int top)
    {
        var scores = new Dictionary<string, int>();
        foreach (var name in graph.Nodes.Keys) scores[name] = 0;
        foreach (var (_, edges) in graph.Edges)
            foreach (var edge in edges)
                if (edge.Kind != EdgeKind.Inheritance && scores.ContainsKey(edge.To))
                    scores[edge.To]++;

        var ranked = scores
            .OrderByDescending(kv => kv.Value)
            .Where(kv => kv.Value > 0)
            .Take(top)
            .ToList();

        AnsiConsole.MarkupLine("[yellow]── Top Classes by Coupling (in-degree, excluding inheritance)[/]");

        if (!ranked.Any())
        {
            AnsiConsole.MarkupLine("[gray]No references collected[/]\n");
            return;
        }

        var table = new Table()
            .Border(TableBorder.Simple)
            .AddColumn(new TableColumn("Rank").RightAligned())
            .AddColumn("Class")
            .AddColumn("Namespace")
            .AddColumn(new TableColumn("Ref Count").RightAligned());

        for (int i = 0; i < ranked.Count; i++)
        {
            var (name, score) = ranked[i];
            var ns = graph.Nodes.TryGetValue(name, out var node) ? node.Namespace : "";
            var color = score >= 10 ? "red" : score >= 5 ? "yellow" : "green";
            table.AddRow($"{i + 1}", Markup.Escape(name), Markup.Escape(ns), $"[{color}]{score}[/]");
        }

        AnsiConsole.Write(table);
        AnsiConsole.WriteLine();
    }

    private void PrintNamespaceSummary(DependencyGraph graph)
    {
        AnsiConsole.MarkupLine("[blue]── Class Distribution by Namespace[/]");

        var nsGroups = graph.Nodes.Values
            .GroupBy(n => string.IsNullOrEmpty(n.Namespace) ? "(None)" : n.Namespace)
            .OrderByDescending(g => g.Count())
            .ToList();

        var table = new Table()
            .Border(TableBorder.Simple)
            .AddColumn("Namespace")
            .AddColumn(new TableColumn("Class Count").RightAligned())
            .AddColumn("Class List");

        foreach (var g in nsGroups)
        {
            var names = string.Join(", ", g.Select(n => n.Name).OrderBy(x => x));
            var truncated = names.Length > 60 ? names[..57] + "..." : names;
            table.AddRow(Markup.Escape(g.Key), g.Count().ToString(), Markup.Escape(truncated));
        }

        AnsiConsole.Write(table);
        AnsiConsole.WriteLine();
    }

    private void PrintCycles(DependencyGraph graph)
    {
        AnsiConsole.MarkupLine("[red]── Detecting Circular References[/]");

        var cycles = graph.FindCyclesDeduped();
        if (!cycles.Any())
        {
            AnsiConsole.MarkupLine("[green]No circular references found[/]");
            return;
        }

        AnsiConsole.MarkupLine($"[yellow]{cycles.Count} circular references found[/]\n");

        var direct = cycles.Where(c => c.Count <= 3).ToList();
        var indirect = cycles.Where(c => c.Count > 3).ToList();

        if (direct.Any())
        {
            AnsiConsole.MarkupLine("[red bold]Direct Cycle[/]");
            foreach (var cycle in direct)
                AnsiConsole.MarkupLine("  [red]↻[/] " + FormatCycle(cycle));
        }

        if (indirect.Any())
        {
            AnsiConsole.WriteLine();
            AnsiConsole.MarkupLine("[yellow bold]Indirect Cycle[/]");
            foreach (var cycle in indirect)
                AnsiConsole.MarkupLine("  [yellow]↻[/] " + FormatCycle(cycle));
        }
    }

    private string FormatCycle(List<(string node, Edge? incomingEdge)> cycle)
    {
        var parts = new List<string>();
        for (int i = 0; i < cycle.Count - 1; i++)
        {
            var (node, edge) = cycle[i];
            parts.Add(Markup.Escape(node));
            if (edge != null)
            {
                var arrow = edge.Kind switch
                {
                    EdgeKind.Inheritance => "[gray]:[/]",
                    EdgeKind.Field => "[gray].[/]",
                    EdgeKind.Property => "[gray]..[/]",
                    _ => "[gray]→[/]"
                };
                var hint = string.IsNullOrEmpty(edge.MemberName)
                    ? "" : $"[gray]({Markup.Escape(edge.MemberName)})[/]";
                parts.Add($"{arrow}{hint}");
            }
        }
        parts.Add(Markup.Escape(cycle[^1].node));
        return string.Join(" ", parts);
    }
}