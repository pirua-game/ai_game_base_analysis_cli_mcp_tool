using gdep.Parser;

namespace gdep.Commands;

/// <summary>
/// path 커맨드: sourceClass.sourceMethod에서 targetClass.targetMethod까지의 최단 호출 경로를 BFS로 탐색한다.
/// </summary>
public class PathCommand
{
    private static readonly HashSet<string> IgnoredDirs = new(StringComparer.OrdinalIgnoreCase)
    {
        "obj", "bin", "Library", "Packages", "Temp", "Build",
        ".vs", ".git", "node_modules",
    };

    public void Execute(string path, string fromClass, string fromMethod,
                       string toClass, string toMethod, int maxDepth = 10)
    {
        if (!Directory.Exists(path))
        {
            Console.WriteLine($"Path not found: {path}");
            return;
        }

        var csFiles = Directory.GetFiles(path, "*.cs", SearchOption.AllDirectories)
            .Where(f => !f.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                          .Any(part => IgnoredDirs.Contains(part)))
            .ToList();

        var analyzer = new MethodCallAnalyzer();
        analyzer.LoadHints(path);
        analyzer.BuildIndex(csFiles);

        var result = analyzer.FindPath(fromClass, fromMethod, toClass, toMethod, maxDepth);

        Console.WriteLine($"── Call Path: {fromClass}.{fromMethod} → {toClass}.{toMethod} ──");
        Console.WriteLine();

        if (result == null || result.Count == 0)
        {
            Console.WriteLine($"No path found (depth limit: {maxDepth})");
            return;
        }

        Console.WriteLine($"Path ({result.Count} steps):");
        for (int i = 0; i < result.Count; i++)
        {
            var (cls, method, cond) = result[i];
            var condStr = cond is not null ? $" [{cond}]" : "";
            var arrow = i < result.Count - 1 ? " →" : "";
            Console.WriteLine($"  {cls}.{method}{condStr}{arrow}");
        }
    }
}
