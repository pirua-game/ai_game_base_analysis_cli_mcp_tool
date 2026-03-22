using Spectre.Console;
using gdep.Graph;

namespace gdep.Commands;

public class ImpactCommand
{
    private readonly ScanCommand _scanCommand = new();
    private readonly Dictionary<string, List<string>> _reverseEdges = new();
    private DependencyGraph _graph = new();

    public void Execute(string path, string targetClass, int maxDepth = 3, bool deep = true)
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            return;
        }

        AnsiConsole.Status()
            .Start("[teal]Building dependency graph...[/]", ctx =>
            {
                _graph = _scanCommand.BuildGraph(path, deep: deep);
                BuildReverseEdges();
            });

        if (!_graph.Nodes.ContainsKey(targetClass))
        {
            AnsiConsole.MarkupLine($"[red]Class '{targetClass}' not found in the project.[/]");
            return;
        }

        AnsiConsole.MarkupLine($"[yellow]── Impact Analysis for: [bold]{targetClass}[/] (Depth: {maxDepth})[/]");
        
        var visited = new HashSet<string>();
        PrintImpactTree(targetClass, 0, maxDepth, visited, "");
    }

    private void BuildReverseEdges()
    {
        foreach (var node in _graph.Nodes.Keys)
        {
            if (!_reverseEdges.ContainsKey(node))
                _reverseEdges[node] = new List<string>();
        }

        foreach (var kvp in _graph.Edges)
        {
            string from = kvp.Key;
            foreach (var edge in kvp.Value)
            {
                if (!_reverseEdges.ContainsKey(edge.To))
                    _reverseEdges[edge.To] = new List<string>();
                
                if (!_reverseEdges[edge.To].Contains(from))
                    _reverseEdges[edge.To].Add(from);
            }
        }
    }

    private void PrintImpactTree(string current, int depth, int maxDepth, HashSet<string> visited, string indent)
    {
        var node = _graph.Nodes[current];
        string fileName = Path.GetFileName(node.FilePath);
        
        if (depth == 0)
        {
            AnsiConsole.MarkupLine($"[bold teal]{current}[/] [gray]({fileName})[/]");
        }

        if (depth >= maxDepth) return;

        visited.Add(current);

        if (_reverseEdges.TryGetValue(current, out var dependents))
        {
            var sortedDependents = dependents.OrderBy(x => x).ToList();
            for (int i = 0; i < sortedDependents.Count; i++)
            {
                string dep = sortedDependents[i];
                bool isLast = (i == sortedDependents.Count - 1);
                string connector = isLast ? "└── " : "├── ";
                string nextIndent = indent + (isLast ? "    " : "│   ");

                var depNode = _graph.Nodes[dep];
                string depFile = Path.GetFileName(depNode.FilePath);

                if (visited.Contains(dep))
                {
                    AnsiConsole.Markup($"{indent}{connector}[yellow]{dep}[/] [gray]({depFile}) [[RECURSIVE]][/]");
                    AnsiConsole.WriteLine();
                    continue;
                }

                AnsiConsole.Markup($"{indent}{connector}[white]{dep}[/] [gray]({depFile})[/]");
                AnsiConsole.WriteLine();

                PrintImpactTree(dep, depth + 1, maxDepth, visited, nextIndent);
            }
        }
        
        visited.Remove(current);
    }
}