namespace gdep.Graph;

public enum EdgeKind { Inheritance, Field, Property, Parameter }

public class Edge
{
    public string To { get; set; } = "";
    public EdgeKind Kind { get; set; }
    public string MemberName { get; set; } = "";
}

public class ClassNode
{
    public string Name { get; set; } = "";
    public string FilePath { get; set; } = "";
    public string Namespace { get; set; } = "";
    public List<string> BaseTypes { get; set; } = new();
}

public class DependencyGraph
{
    private readonly Dictionary<string, ClassNode> _nodes = new();
    private readonly Dictionary<string, List<Edge>> _edges = new();

    public void AddNode(ClassNode node)
    {
        if (!_nodes.ContainsKey(node.Name))
        {
            _nodes[node.Name] = node;
            _edges[node.Name] = new List<Edge>();
        }
        else
        {
            foreach (var bt in node.BaseTypes)
                if (!_nodes[node.Name].BaseTypes.Contains(bt))
                    _nodes[node.Name].BaseTypes.Add(bt);
        }
    }

    public void AddEdge(string from, string to, EdgeKind kind, string memberName = "")
    {
        if (from == to) return;
        if (!_edges.ContainsKey(from))
            _edges[from] = new List<Edge>();

        // 같은 (to, kind) 조합 중복 제거
        if (!_edges[from].Any(e => e.To == to && e.Kind == kind))
            _edges[from].Add(new Edge { To = to, Kind = kind, MemberName = memberName });
    }

    public IReadOnlyDictionary<string, ClassNode> Nodes => _nodes;
    public IReadOnlyDictionary<string, List<Edge>> Edges => _edges;

    public List<string> GetAncestorChain(string className, int maxDepth = 20)
    {
        var chain = new List<string>();
        var current = className;
        var visited = new HashSet<string>();
        for (int i = 0; i < maxDepth; i++)
        {
            if (visited.Contains(current)) break;
            visited.Add(current);
            if (!_nodes.TryGetValue(current, out var node) || !node.BaseTypes.Any())
                break;
            chain.Add(node.BaseTypes[0]);
            current = node.BaseTypes[0];
        }
        return chain;
    }

    // 결합도: in-degree, 상속 엣지 제외 옵션
    public Dictionary<string, int> GetCouplingScores(bool excludeInheritance = true)
    {
        var scores = _nodes.Keys.ToDictionary(k => k, _ => 0);
        foreach (var (_, edges) in _edges)
            foreach (var edge in edges)
            {
                if (excludeInheritance && edge.Kind == EdgeKind.Inheritance) continue;
                if (scores.ContainsKey(edge.To))
                    scores[edge.To]++;
            }
        return scores;
    }

    public List<string> GetDeadNodes()
    {
        var referenced = new HashSet<string>();
        foreach (var (_, edges) in _edges)
            foreach (var edge in edges)
                referenced.Add(edge.To);

        return _nodes.Keys
            .Where(k => !referenced.Contains(k))
            .OrderBy(k => k)
            .ToList();
    }

    public void RemoveProtoNodes()
    {
        var protoKeys = _nodes.Keys.Where(k => k.EndsWith("_PROTO")).ToList();
        foreach (var key in protoKeys)
        {
            _nodes.Remove(key);
            _edges.Remove(key);
            foreach (var edges in _edges.Values)
                edges.RemoveAll(e => e.To == key);
        }
    }

    public List<List<(string node, Edge? incomingEdge)>> FindCycles()
    {
        var cycles = new List<List<(string, Edge?)>>();
        var visited = new HashSet<string>();
        var stack = new HashSet<string>();
        var path = new List<(string node, Edge? edge)>();

        foreach (var node in _nodes.Keys)
            if (!visited.Contains(node))
                Dfs(node, visited, stack, path, cycles);

        return cycles;
    }

    public List<List<(string node, Edge? incomingEdge)>> FindCyclesDeduped()
    {
        var all = FindCycles();
        var seen = new HashSet<string>();
        var result = new List<List<(string, Edge?)>>();

        foreach (var cycle in all.OrderBy(c => c.Count))
        {
            var key = string.Join(",", cycle.Select(x => x.node).Distinct().OrderBy(x => x));
            if (seen.Add(key))
                result.Add(cycle);
        }

        return result;
    }

    private void Dfs(string node, HashSet<string> visited, HashSet<string> stack,
        List<(string node, Edge? edge)> path, List<List<(string, Edge?)>> cycles)
    {
        visited.Add(node);
        stack.Add(node);
        path.Add((node, null));

        if (_edges.TryGetValue(node, out var neighbors))
        {
            foreach (var edge in neighbors)
            {
                if (!visited.Contains(edge.To))
                {
                    path[^1] = (path[^1].node, edge);
                    Dfs(edge.To, visited, stack, path, cycles);
                    path[^1] = (path[^1].node, null);
                }
                else if (stack.Contains(edge.To))
                {
                    var cycleStart = path.FindIndex(p => p.node == edge.To);
                    var cycle = path[cycleStart..].ToList();
                    cycle[^1] = (cycle[^1].node, edge);
                    cycle.Add((edge.To, null));
                    cycles.Add(cycle);
                }
            }
        }

        stack.Remove(node);
        path.RemoveAt(path.Count - 1);
    }
}