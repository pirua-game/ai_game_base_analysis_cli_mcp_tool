using Spectre.Console;
using gdep.Graph;
using gdep.Parser;

namespace gdep.Commands;

public class GraphCommand
{
    private readonly CSharpParser _parser = new();

    public void Execute(string path, string format, string? outputFile,
        bool skipProto = true, bool cyclesOnly = false, bool noIsolated = false)
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            return;
        }

        var graph = new DependencyGraph();
        var csFiles = Directory.GetFiles(path, "*.cs", SearchOption.AllDirectories);

        if (skipProto)
            csFiles = csFiles.Where(f => !Path.GetFileName(f).EndsWith("_PROTO.cs")).ToArray();

        AnsiConsole.Progress().Start(ctx =>
        {
            var task = ctx.AddTask("[teal]Scanning...[/]", maxValue: 1);
            var parsed = _parser.ParseFiles(csFiles);
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

        // Determine circular reference node set first
        var allCycleNodes = graph.FindCyclesDeduped()
            .SelectMany(c => c.Select(x => x.node))
            .ToHashSet();

        // --cycles-only: only nodes included in cycles
        var includedNodes = graph.Nodes.Keys.ToHashSet();
        if (cyclesOnly)
            includedNodes = allCycleNodes;

        // --no-isolated: exclude nodes with no edges
        if (noIsolated)
        {
            var connected = new HashSet<string>();
            foreach (var (from, edges) in graph.Edges)
            {
                if (!includedNodes.Contains(from)) continue;
                foreach (var e in edges)
                {
                    if (!includedNodes.Contains(e.To)) continue;
                    connected.Add(from);
                    connected.Add(e.To);
                }
            }
            includedNodes = connected;
        }

        var content = format.ToLower() switch
        {
            "dot" => ExportDot(graph, includedNodes, allCycleNodes),
            _     => ExportMermaid(graph, includedNodes, allCycleNodes)
        };

        if (!string.IsNullOrEmpty(outputFile))
        {
            File.WriteAllText(outputFile, content);
            AnsiConsole.MarkupLine($"\n[green]Saved to:[/] {outputFile}");
            AnsiConsole.MarkupLine($"[gray]{includedNodes.Count} nodes → {outputFile}[/]");
        }
        else
        {
            AnsiConsole.WriteLine();
            Console.WriteLine(content);
        }
    }

    // ── Mermaid ──────────────────────────────────────────────────────────
    private string ExportMermaid(DependencyGraph graph,
        HashSet<string> includedNodes, HashSet<string> cycleNodes)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("graph TD");

        // Node declarations
        foreach (var name in includedNodes)
        {
            var safe = Sanitize(name);
            var label = cycleNodes.Contains(name) ? $"⚠ {name}" : name;
            sb.AppendLine($"  {safe}[\"{label}\"]");
        }

        sb.AppendLine();

        // Edge declarations (only edges within includedNodes)
        foreach (var (from, edges) in graph.Edges)
        {
            if (!includedNodes.Contains(from)) continue;
            foreach (var edge in edges)
            {
                if (!includedNodes.Contains(edge.To)) continue;

                var fromSafe = Sanitize(from);
                var toSafe = Sanitize(edge.To);
                var label = BuildEdgeLabel(edge);
                var arrow = edge.Kind == EdgeKind.Inheritance
                    ? "-->|extends|"
                    : $"-->\"|{label}\"|";

                sb.AppendLine($"  {fromSafe} {arrow} {toSafe}");
            }
        }

        // Highlight cycles
        sb.AppendLine();
        sb.AppendLine("  classDef cycle fill:#FAECE7,stroke:#D85A30,color:#993C1D");
        foreach (var n in cycleNodes.Where(includedNodes.Contains))
            sb.AppendLine($"  class {Sanitize(n)} cycle");

        return sb.ToString();
    }

    // ── DOT (Graphviz) ────────────────────────────────────────────────────
    private string ExportDot(DependencyGraph graph,
        HashSet<string> includedNodes, HashSet<string> cycleNodes)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("digraph gdep {");
        sb.AppendLine("  rankdir=LR;");
        sb.AppendLine("  node [shape=box, style=filled, fontname=\"sans-serif\"];");
        sb.AppendLine("  edge [fontname=\"sans-serif\", fontsize=10];");
        sb.AppendLine();

        // Node declarations
        foreach (var name in includedNodes)
        {
            var attrs = cycleNodes.Contains(name)
                ? "fillcolor=\"#FAECE7\", color=\"#D85A30\", fontcolor=\"#993C1D\""
                : "fillcolor=\"#F1EFE8\", color=\"#888780\"";
            sb.AppendLine($"  \"{name}\" [{attrs}];");
        }

        sb.AppendLine();

        // Edge declarations
        foreach (var (from, edges) in graph.Edges)
        {
            if (!includedNodes.Contains(from)) continue;
            foreach (var edge in edges)
            {
                if (!includedNodes.Contains(edge.To)) continue;

                var label = BuildEdgeLabel(edge);
                var style = edge.Kind switch
                {
                    EdgeKind.Inheritance => "style=dashed, color=\"#7F77DD\"",
                    EdgeKind.Field       => "color=\"#1D9E75\"",
                    EdgeKind.Property    => "color=\"#1D9E75\", style=dotted",
                    _                    => "color=\"#888780\""
                };

                sb.AppendLine($"  \"{from}\" -> \"{edge.To}\" [label=\"{label}\", {style}];");
            }
        }

        sb.AppendLine("}");
        return sb.ToString();
    }

    private string BuildEdgeLabel(Edge edge) => edge.Kind switch
    {
        EdgeKind.Inheritance => "extends",
        EdgeKind.Field       => string.IsNullOrEmpty(edge.MemberName) ? "field" : $".{edge.MemberName}",
        EdgeKind.Property    => string.IsNullOrEmpty(edge.MemberName) ? "prop"  : $"..{edge.MemberName}",
        EdgeKind.Parameter   => string.IsNullOrEmpty(edge.MemberName) ? "param" : edge.MemberName,
        _                    => ""
    };

    private string Sanitize(string name) =>
        name.Replace("-", "_").Replace(".", "_").Replace("<", "_").Replace(">", "_");
}