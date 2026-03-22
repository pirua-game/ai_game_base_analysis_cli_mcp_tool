using System.Diagnostics;
using Spectre.Console;
using gdep.Graph;
using gdep.Parser;

namespace gdep.Commands;

public class DiffCommand
{
    private readonly CSharpParser _parser = new();

    public void Execute(string path, string? commit, bool skipProto = true,
        string[]? ignorePatterns = null, bool failOnNewCycles = false)
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            Environment.Exit(1);
            return;
        }

        // Check git root
        var gitRoot = FindGitRoot(path);
        if (gitRoot == null)
        {
            AnsiConsole.MarkupLine("[red]Git repository not found. Please run within a git-initialized folder.[/]");
            Environment.Exit(1);
            return;
        }

        var baseCommit = commit ?? "HEAD";
        AnsiConsole.MarkupLine($"[gray]Baseline: [white]{baseCommit}[/] vs Current Working Tree[/]");

        // Collect changed cs files
        var changedFiles = GetChangedFiles(gitRoot, path, baseCommit);
        if (changedFiles.Count == 0)
        {
            AnsiConsole.MarkupLine("[green]No changed .cs files found.[/]");
            return;
        }

        AnsiConsole.MarkupLine($"[gray]Detected {changedFiles.Count} changed files[/]\n");

        DependencyGraph? before = null;
        DependencyGraph? after = null;

        AnsiConsole.Progress().Start(ctx =>
        {
            var t1 = ctx.AddTask("[teal]Parsing previous state...[/]", maxValue: 1);
            before = BuildGraphFromCommit(gitRoot, path, baseCommit, changedFiles, skipProto, ignorePatterns);
            t1.Value = 1;

            var t2 = ctx.AddTask("[teal]Parsing current state...[/]", maxValue: 1);
            after = BuildGraphFromWorkingTree(path, skipProto, ignorePatterns);
            t2.Value = 1;
        });

        AnsiConsole.WriteLine();
        PrintDiff(before!, after!, failOnNewCycles);
    }

    // ── Graph Build ──────────────────────────────────────────────

    private DependencyGraph BuildGraphFromCommit(string gitRoot, string scanPath,
        string commit, List<string> changedFiles, bool skipProto, string[]? ignorePatterns)
    {
        // Parse all files, then replace changed files with previous versions from git show
        var allFiles = ScanCommand.CollectFiles(scanPath, skipProto, ignorePatterns);
        var relChanged = changedFiles
            .Select(f => Path.GetFullPath(f))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        // Unchanged files use current version
        var stableFiles = allFiles.Where(f => !relChanged.Contains(Path.GetFullPath(f))).ToList();
        var parsedResults = _parser.ParseFiles(stableFiles);

        // Changed files: parse previous version content from git show via temp files
        var tempDir = Path.Combine(Path.GetTempPath(), "gdep_diff_" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(tempDir);
        try
        {
            foreach (var absPath in relChanged)
            {
                var relPath = Path.GetRelativePath(gitRoot, absPath).Replace('\\', '/');
                var oldContent = RunGit(gitRoot, $"show {commit}:{relPath}");
                if (oldContent == null) continue; // File didn't exist in previous commit (newly added)

                var tempFile = Path.Combine(tempDir, Path.GetFileName(absPath));
                File.WriteAllText(tempFile, oldContent);
                parsedResults.AddRange(_parser.ParseFile(tempFile));
            }

            return BuildGraphFromParsed(parsedResults, skipProto);
        }
        finally
        {
            Directory.Delete(tempDir, recursive: true);
        }
    }

    private DependencyGraph BuildGraphFromWorkingTree(string path, bool skipProto, string[]? ignorePatterns)
    {
        var files = ScanCommand.CollectFiles(path, skipProto, ignorePatterns);
        var parsed = _parser.ParseFiles(files);
        return BuildGraphFromParsed(parsed, skipProto);
    }

    private DependencyGraph BuildGraphFromParsed(List<ParsedType> parsed, bool skipProto)
    {
        var graph = new DependencyGraph();
        foreach (var p in parsed)
        {
            graph.AddNode(p.Node);
            foreach (var edge in p.Edges)
                graph.AddEdge(p.Node.Name, edge.To, edge.Kind, edge.MemberName);
        }
        if (skipProto) graph.RemoveProtoNodes();
        return graph;
    }

    // ── Diff Output ────────────────────────────────────────────────

    private void PrintDiff(DependencyGraph before, DependencyGraph after, bool failOnNewCycles)
    {
        var beforeCycles = before.FindCyclesDeduped()
            .Select(c => CycleKey(c)).ToHashSet();
        var afterCycles = after.FindCyclesDeduped()
            .Select(c => CycleKey(c)).ToHashSet();

        var newCycles    = afterCycles.Except(beforeCycles).ToList();
        var removedCycles = beforeCycles.Except(afterCycles).ToList();

        // Coupling changes
        var beforeScores = CouplingScores(before);
        var afterScores  = CouplingScores(after);
        var couplingChanges = afterScores.Keys.Union(beforeScores.Keys)
            .Select(name => (name,
                before: beforeScores.GetValueOrDefault(name),
                after:  afterScores.GetValueOrDefault(name),
                delta:  afterScores.GetValueOrDefault(name) - beforeScores.GetValueOrDefault(name)))
            .Where(x => x.delta != 0)
            .OrderByDescending(x => Math.Abs(x.delta))
            .Take(10)
            .ToList();

        // New/Removed classes
        var newNodes     = after.Nodes.Keys.Except(before.Nodes.Keys).ToList();
        var removedNodes = before.Nodes.Keys.Except(after.Nodes.Keys).ToList();

        // ── Output
        PrintSummaryBox(newNodes, removedNodes, newCycles, removedCycles, couplingChanges);

        if (newNodes.Any() || removedNodes.Any())
            PrintNodeChanges(newNodes, removedNodes);

        if (couplingChanges.Any())
            PrintCouplingChanges(couplingChanges);

        if (newCycles.Any() || removedCycles.Any())
            PrintCycleChanges(newCycles, removedCycles, after);

        // CI: Fail if new circular references are detected
        if (failOnNewCycles && newCycles.Any())
        {
            AnsiConsole.MarkupLine("\n[red bold]New circular reference detected. Treating as CI failure.[/]");
            Environment.Exit(1);
        }
    }

    private void PrintSummaryBox(List<string> newNodes, List<string> removedNodes,
        List<string> newCycles, List<string> removedCycles,
        List<(string name, int before, int after, int delta)> couplingChanges)
    {
        var lines = new List<string>();

        if (newNodes.Any())
            lines.Add($"[green]+{newNodes.Count} classes added[/]");
        if (removedNodes.Any())
            lines.Add($"[red]-{removedNodes.Count} classes removed[/]");
        if (newCycles.Any())
            lines.Add($"[red]↻ +{newCycles.Count} circular references added[/]");
        if (removedCycles.Any())
            lines.Add($"[green]↻ -{removedCycles.Count} circular references resolved[/]");
        if (couplingChanges.Any(x => x.delta > 0))
            lines.Add($"[yellow]Coupling increased for {couplingChanges.Count(x => x.delta > 0)} classes[/]");
        if (couplingChanges.Any(x => x.delta < 0))
            lines.Add($"[green]Coupling decreased for {couplingChanges.Count(x => x.delta < 0)} classes[/]");

        if (!lines.Any())
            lines.Add("[green]No dependency changes[/]");

        var panel = new Panel(string.Join("  |  ", lines))
        {
            Header = new PanelHeader("[teal] gdep diff results [/]"),
            Border = BoxBorder.Rounded
        };
        AnsiConsole.Write(panel);
        AnsiConsole.WriteLine();
    }

    private void PrintNodeChanges(List<string> newNodes, List<string> removedNodes)
    {
        if (newNodes.Any())
        {
            AnsiConsole.MarkupLine("[green]── Added Classes[/]");
            foreach (var n in newNodes)
                AnsiConsole.MarkupLine($"  [green]+[/] {Markup.Escape(n)}");
            AnsiConsole.WriteLine();
        }

        if (removedNodes.Any())
        {
            AnsiConsole.MarkupLine("[red]── Removed Classes[/]");
            foreach (var n in removedNodes)
                AnsiConsole.MarkupLine($"  [red]-[/] {Markup.Escape(n)}");
            AnsiConsole.WriteLine();
        }
    }

    private void PrintCouplingChanges(List<(string name, int before, int after, int delta)> changes)
    {
        AnsiConsole.MarkupLine("[yellow]── Top 10 Coupling Changes[/]");

        var table = new Table()
            .Border(TableBorder.Simple)
            .AddColumn("Class")
            .AddColumn(new TableColumn("Prev").RightAligned())
            .AddColumn(new TableColumn("Curr").RightAligned())
            .AddColumn(new TableColumn("Delta").RightAligned());

        foreach (var (name, bef, aft, delta) in changes)
        {
            var deltaStr = delta > 0 ? $"[red]+{delta}[/]" : $"[green]{delta}[/]";
            table.AddRow(Markup.Escape(name), bef.ToString(), aft.ToString(), deltaStr);
        }

        AnsiConsole.Write(table);
        AnsiConsole.WriteLine();
    }

    private void PrintCycleChanges(List<string> newCycles, List<string> removedCycles, DependencyGraph after)
    {
        if (newCycles.Any())
        {
            AnsiConsole.MarkupLine("[red bold]── New Circular References[/]");
            foreach (var key in newCycles)
                AnsiConsole.MarkupLine($"  [red]↻[/] {Markup.Escape(key)}");
            AnsiConsole.WriteLine();
        }

        if (removedCycles.Any())
        {
            AnsiConsole.MarkupLine("[green bold]── Resolved Circular References[/]");
            foreach (var key in removedCycles)
                AnsiConsole.MarkupLine($"  [green]✓[/] {Markup.Escape(key)}");
            AnsiConsole.WriteLine();
        }
    }

    // ── Utils ────────────────────────────────────────────────────

    private string CycleKey(List<(string node, Edge? edge)> cycle) =>
        string.Join(" → ", cycle.Select(x => x.node).Distinct().OrderBy(x => x));

    private Dictionary<string, int> CouplingScores(DependencyGraph graph)
    {
        var scores = graph.Nodes.Keys.ToDictionary(k => k, _ => 0);
        foreach (var (_, edges) in graph.Edges)
            foreach (var edge in edges)
                if (edge.Kind != EdgeKind.Inheritance && scores.ContainsKey(edge.To))
                    scores[edge.To]++;
        return scores;
    }

    private List<string> GetChangedFiles(string gitRoot, string scanPath, string commit)
    {
        // git diff for list of changed files
        var output = RunGit(gitRoot, $"diff --name-only {commit} -- .");
        if (output == null) return new List<string>();

        var absPath = Path.GetFullPath(scanPath);
        return output
            .Split('\n', StringSplitOptions.RemoveEmptyEntries)
            .Where(f => f.EndsWith(".cs", StringComparison.OrdinalIgnoreCase))
            .Select(f => Path.Combine(gitRoot, f.Replace('/', Path.DirectorySeparatorChar)))
            .Where(f => Path.GetFullPath(f).StartsWith(absPath, StringComparison.OrdinalIgnoreCase))
            .ToList();
    }

    private string? RunGit(string workDir, string args)
    {
        try
        {
            var psi = new ProcessStartInfo("git", args)
            {
                WorkingDirectory = workDir,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            using var proc = Process.Start(psi)!;
            var output = proc.StandardOutput.ReadToEnd();
            proc.WaitForExit();
            return proc.ExitCode == 0 ? output : null;
        }
        catch { return null; }
    }

    private string? FindGitRoot(string startPath)
    {
        var dir = new DirectoryInfo(Path.GetFullPath(startPath));
        while (dir != null)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, ".git")))
                return dir.FullName;
            dir = dir.Parent;
        }
        return null;
    }
}