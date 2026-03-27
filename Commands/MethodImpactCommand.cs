using gdep.Parser;

namespace gdep.Commands;

/// <summary>
/// method-impact 커맨드: targetClass.targetMethod를 호출하는 모든 메서드를 역방향 탐색한다.
/// </summary>
public class MethodImpactCommand
{
    private static readonly HashSet<string> IgnoredDirs = new(StringComparer.OrdinalIgnoreCase)
    {
        "obj", "bin", "Library", "Packages", "Temp", "Build",
        ".vs", ".git", "node_modules",
    };

    public void Execute(string path, string targetClass, string targetMethod)
    {
        if (!Directory.Exists(path))
        {
            Console.WriteLine($"Path not found: {path}");
            return;
        }

        // .cs 파일 수집 (무시 폴더 제외)
        var csFiles = Directory.GetFiles(path, "*.cs", SearchOption.AllDirectories)
            .Where(f => !f.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                          .Any(part => IgnoredDirs.Contains(part)))
            .ToList();

        // 메서드 인덱스 빌드
        var analyzer = new MethodCallAnalyzer();
        analyzer.LoadHints(path);
        analyzer.BuildIndex(csFiles);

        // 역방향 탐색
        var callers = analyzer.FindCallers(targetClass, targetMethod);

        // 출력
        Console.WriteLine($"── Method Impact: {targetClass}::{targetMethod} ──");
        Console.WriteLine();

        if (callers.Count == 0)
        {
            Console.WriteLine($"No callers found for {targetClass}.{targetMethod}");
            return;
        }

        Console.WriteLine($"Called by {callers.Count} method(s):");
        foreach (var (cls, method, cond) in callers)
        {
            var condStr = cond is not null ? $" [{cond}]" : "";
            Console.WriteLine($"  \u2190 {cls}::{method}{condStr}");
        }
    }
}
