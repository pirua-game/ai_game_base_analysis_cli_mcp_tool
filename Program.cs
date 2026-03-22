using gdep.Commands;

if (args.Length == 0 || args[0] == "--help" || args[0] == "-h")
{
    PrintHelp();
    return 0;
}

// ── scan ──────────────────────────────────────────────────────
if (args[0] == "scan")
{
    if (args.Length < 2) { Console.WriteLine("Usage: gdep scan <path> [options]"); return 1; }
    var path           = args[1];
    var showCycles     = args.Contains("--circular");
    var includeProto   = args.Contains("--include-proto");
    var showNamespaces = args.Contains("--namespaces");
    var showDeadCode   = args.Contains("--dead-code");
    var deep           = args.Contains("--deep");
    var top            = ParseIntOption(args, "--top", 10);
    var ignorePatterns = ParseMultiOption(args, "--ignore");
    var nsFilter       = ParseStringOption(args, "--namespace");
    var format         = ParseStringOption(args, "--format") ?? "console";
    new ScanCommand().Execute(path, showCycles, top, skipProto: !includeProto,
        ignorePatterns: ignorePatterns, namespaceFilter: nsFilter, showNamespaces: showNamespaces,
        showDeadCode: showDeadCode, deep: deep, format: format);
    return 0;
}

// ── graph ─────────────────────────────────────────────────────
if (args[0] == "graph")
{
    if (args.Length < 2) { Console.WriteLine("Usage: gdep graph <path> [options]"); return 1; }
    var path         = args[1];
    var includeProto = args.Contains("--include-proto");
    var cyclesOnly   = args.Contains("--cycles-only");
    var noIsolated   = args.Contains("--no-isolated");
    var format       = ParseStringOption(args, "--format") ?? "mermaid";
    var outputFile   = ParseStringOption(args, "--output");
    if (!string.IsNullOrEmpty(outputFile) && !Path.HasExtension(outputFile))
        outputFile += format == "dot" ? ".dot" : ".md";
    new GraphCommand().Execute(path, format, outputFile,
        skipProto: !includeProto, cyclesOnly: cyclesOnly, noIsolated: noIsolated);
    return 0;
}

// ── diff ──────────────────────────────────────────────────────
if (args[0] == "diff")
{
    if (args.Length < 2) { Console.WriteLine("Usage: gdep diff <path> [options]"); return 1; }
    var path            = args[1];
    var includeProto    = args.Contains("--include-proto");
    var failOnNewCycles = args.Contains("--fail-on-cycles");
    var commit          = ParseStringOption(args, "--commit");
    var ignorePatterns  = ParseMultiOption(args, "--ignore");
    new DiffCommand().Execute(path, commit, skipProto: !includeProto,
        ignorePatterns: ignorePatterns, failOnNewCycles: failOnNewCycles);
    return 0;
}

// ── describe ──────────────────────────────────────────────────
if (args[0] == "describe")
{
    if (args.Length < 3) { Console.WriteLine("Usage: gdep describe <path> <className> [options]"); return 1; }
    var path           = args[1];
    var className      = args[2];
    var includeProto   = args.Contains("--include-proto");
    var format         = ParseStringOption(args, "--format") ?? "console";
    var outputFile     = ParseStringOption(args, "--output");
    var ignorePatterns = ParseMultiOption(args, "--ignore");
    new DescribeCommand().Execute(path, className, outputFile,
        format: format, skipProto: !includeProto, ignorePatterns: ignorePatterns);
    return 0;
}

// ── flow ──────────────────────────────────────────────────────
if (args[0] == "flow")
{
    if (args.Length < 2) { Console.WriteLine("Usage: gdep flow <path> [options]"); return 1; }
    var path           = args[1];
    var className      = ParseStringOption(args, "--class")  ?? "";
    var methodName     = ParseStringOption(args, "--method") ?? "";
    var depth          = ParseIntOption(args, "--depth", 4);
    var format         = ParseStringOption(args, "--format") ?? "console";
    var outputFile     = ParseStringOption(args, "--output");
    var includeProto   = args.Contains("--include-proto");
    var ignorePatterns = ParseMultiOption(args, "--ignore");
    var focusRaw       = ParseMultiOption(args, "--focus-class");
    var focusClasses   = focusRaw
        .SelectMany(s => s.Split(',', StringSplitOptions.RemoveEmptyEntries))
        .Select(s => s.Trim()).ToArray();

    if (string.IsNullOrEmpty(className) || string.IsNullOrEmpty(methodName))
    {
        Console.WriteLine("--class and --method options are required.");
        return 1;
    }
    new FlowCommand().Execute(path, className, methodName,
        maxDepth: depth, format: format, outputFile: outputFile,
        skipProto: !includeProto, ignorePatterns: ignorePatterns,
        focusClasses: focusClasses.Length > 0 ? focusClasses : null);
    return 0;
}

// ── impact ────────────────────────────────────────────────────
if (args[0] == "impact")
{
    if (args.Length < 3) { Console.WriteLine("Usage: gdep impact <path> <targetClass> [options]"); return 1; }
    var path        = args[1];
    var targetClass = args[2];
    var depth       = ParseIntOption(args, "--depth", 3);
    var deep        = args.Contains("--deep");
    new ImpactCommand().Execute(path, targetClass, maxDepth: depth, deep: deep);
    return 0;
}

// ── lint ──────────────────────────────────────────────────────
if (args[0] == "lint")
{
    if (args.Length < 2) { Console.WriteLine("Usage: gdep lint <path> [options]"); return 1; }
    var path           = args[1];
    var includeProto   = args.Contains("--include-proto");
    var ignorePatterns = ParseMultiOption(args, "--ignore");
    new LintCommand().Execute(path, ignorePatterns: ignorePatterns, skipProto: !includeProto);
    return 0;
}

// ── hints ─────────────────────────────────────────────────────
if (args[0] == "hints")
{
    if (args.Length < 2) { Console.WriteLine("Usage: gdep hints <subcommand> <path>"); return 1; }

    var sub  = args[1];
    var path = args.Length > 2 ? args[2] : Directory.GetCurrentDirectory();

    if (sub == "generate")
    {
        var outputFile     = ParseStringOption(args, "--output");
        var ignorePatterns = ParseMultiOption(args, "--ignore");
        var includeProto   = args.Contains("--include-proto");
        new HintsCommand().Generate(path, outputFile,
            skipProto: !includeProto, ignorePatterns: ignorePatterns);
        return 0;
    }

    if (sub == "show")
    {
        new HintsCommand().Show(path);
        return 0;
    }

    Console.WriteLine($"Unknown hints subcommand: {sub}");
    Console.WriteLine("Available: generate | show");
    return 1;
}

Console.WriteLine($"Unknown command: {args[0]}");
PrintHelp();
return 1;

// ── Option Parser Utils ────────────────────────────────────────────
int ParseIntOption(string[] args, string key, int defaultVal)
{
    var idx = Array.IndexOf(args, key);
    if (idx >= 0 && idx + 1 < args.Length && int.TryParse(args[idx + 1], out var v)) return v;
    return defaultVal;
}
string? ParseStringOption(string[] args, string key)
{
    var idx = Array.IndexOf(args, key);
    return idx >= 0 && idx + 1 < args.Length ? args[idx + 1] : null;
}
string[] ParseMultiOption(string[] args, string key)
{
    var result = new List<string>();
    for (int i = 0; i < args.Length - 1; i++)
        if (args[i] == key) result.Add(args[i + 1]);
    return result.ToArray();
}

void PrintHelp()
{
    Console.WriteLine("gdep - Game Dependency Analyzer");
    Console.WriteLine();
    Console.WriteLine("Commands:");
    Console.WriteLine("  scan     <path>              Dependency analysis and report");
    Console.WriteLine("    --circular              Detect circular references");
    Console.WriteLine("    --dead-code             Detect orphan nodes (0 references)");
    Console.WriteLine("    --deep                  Deep analysis including method bodies");
    Console.WriteLine("    --top <N>               Output top N classes by coupling (default: 10)");
    Console.WriteLine("    --namespace <ns>        Filter by specific namespace");
    Console.WriteLine("    --ignore <pattern>      File patterns to ignore (wildcards supported)");
    Console.WriteLine("    --include-proto         Include _PROTO.cs files");
    Console.WriteLine("  graph    <path>              Export dependency graph");
    Console.WriteLine("  diff     <path>              Detect changes between git commits");
    Console.WriteLine("  describe <path> <className>   Detailed class visualization");
    Console.WriteLine("  flow     <path>              Track method call flow");
    Console.WriteLine("  impact   <path> <className>   Impact analysis for a specific class");
    Console.WriteLine("    --depth <N>             Impact tracing depth (default: 3)");
    Console.WriteLine("    --deep                  Analyze dependencies inside method bodies");
    Console.WriteLine("  lint     <path>              Scan for game-specific anti-patterns (Unity)");
    Console.WriteLine("  hints    <subcommand> <path> Manage hint files");
    Console.WriteLine();
    Console.WriteLine("Flow Options:");
    Console.WriteLine("  --class <class>          Entry point class name (Required)");
    Console.WriteLine("  --method <method>         Entry point method name (Required)");
    Console.WriteLine("  --depth <N>               Tracing depth (default: 4)");
    Console.WriteLine("  --focus-class <class>    Classes for deep tracing (comma-separated or repeated)");
    Console.WriteLine("  --format <fmt>            console (default) | mermaid | dot");
    Console.WriteLine("  --output <file>           Output file path");
    Console.WriteLine();
    Console.WriteLine("Hints Subcommands:");
    Console.WriteLine("  generate <path>   Detect static accessor patterns in code and generate .gdep-hints.json");
    Console.WriteLine("  show <path>       Check current hint file content");
    Console.WriteLine();
    Console.WriteLine("Hint File Format (.gdep-hints.json):");
    Console.WriteLine("  {");
    Console.WriteLine("    \"staticAccessors\": {");
    Console.WriteLine("      \"Managers\": {");
    Console.WriteLine("        \"UI\":       \"ManagerUI\",");
    Console.WriteLine("        \"Sound\":    \"ManagerSound\",");
    Console.WriteLine("        \"Dialog\":   \"ManagerDialog\",");
    Console.WriteLine("        \"UserData\": \"ManagerUserData\",");
    Console.WriteLine("        \"Backend\":  \"ManagerBackend\"");
    Console.WriteLine("      }");
    Console.WriteLine("    }");
    Console.WriteLine("  }");
    Console.WriteLine();
    Console.WriteLine("Example:");
    Console.WriteLine("  # Generate hint file automatically and fill types manually");
    Console.WriteLine("  gdep hints generate D:\\...\\Assets\\Scripts");
    Console.WriteLine();
    Console.WriteLine("  # Run flow after applying hints");
    Console.WriteLine("  gdep flow D:\\...\\Scripts --class ManagerBattle --method PlayHand --depth 4");
}