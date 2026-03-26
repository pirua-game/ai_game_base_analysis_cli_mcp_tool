using Spectre.Console;
using gdep.Graph;
using gdep.Parser;

namespace gdep.Commands;

public class DescribeCommand
{
    private readonly CSharpParser _parser = new();

    public void Execute(string path, string className, string? outputFile,
        string format = "console", bool skipProto = true, string[]? ignorePatterns = null)
    {
        if (!Directory.Exists(path))
        {
            AnsiConsole.MarkupLine($"[red]Path not found: {path}[/]");
            return;
        }

        var csFiles = ScanCommand.CollectFiles(path, skipProto, ignorePatterns);

        List<ParsedType> allParsed = new();
        AnsiConsole.Progress().Start(ctx =>
        {
            var task = ctx.AddTask("[teal]Scanning...[/]", maxValue: 1);
            allParsed = _parser.ParseFiles(csFiles);
            task.Value = 1;
        });

        if (skipProto)
            allParsed = allParsed
                .Where(p => !p.Node.Name.EndsWith("_PROTO"))
                .ToList();

        // Search for target class (including partial matches)
        var targets = allParsed
            .Where(p => p.Node.Name.Equals(className, StringComparison.OrdinalIgnoreCase))
            .ToList();

        if (!targets.Any())
        {
            // Retry partial match
            targets = allParsed
                .Where(p => p.Node.Name.Contains(className, StringComparison.OrdinalIgnoreCase))
                .ToList();

            if (!targets.Any())
            {
                AnsiConsole.MarkupLine($"[red]Class not found: {className}[/]");
                return;
            }

            if (targets.Count > 1)
            {
                AnsiConsole.MarkupLine($"[yellow]Multiple classes match. Please enter a more specific name:[/]");
                foreach (var t in targets)
                    AnsiConsole.MarkupLine($"  - {t.Node.Name} ({t.Node.Namespace})");
                return;
            }
        }

        // Partial classes are already merged by the parser, so use the first result
        var target = targets.First();

        // in-degree: list of classes referring to this class
        var referencedBy = allParsed
            .Where(p => p.Edges.Any(e =>
                e.To == target.Node.Name && e.Kind != EdgeKind.Inheritance))
            .Select(p => p.Node.Name)
            .Distinct()
            .OrderBy(x => x)
            .ToList();

        AnsiConsole.WriteLine();

        if (format == "console")
        {
            PrintConsole(target, referencedBy, allParsed);
        }
        else
        {
            var content = format == "dot"
                ? ExportDot(target, referencedBy)
                : ExportMermaid(target, referencedBy);

            if (!string.IsNullOrEmpty(outputFile))
            {
                if (!Path.HasExtension(outputFile))
                    outputFile += format == "dot" ? ".dot" : ".md";
                File.WriteAllText(outputFile, content);
                AnsiConsole.MarkupLine($"[green]Saved to:[/] {outputFile}");
            }
            else
            {
                Console.WriteLine(content);
            }
        }
    }

    // ── Console Output ────────────────────────────────────────────────

    private void PrintConsole(ParsedType t, List<string> referencedBy, List<ParsedType> allParsed)
    {
        var node = t.Node;
        var kindLabel = t.TypeKind switch
        {
            "struct"    => "[blue]struct[/]",
            "interface" => "[purple]interface[/]",
            _           => "[teal]class[/]"
        };

        // Header
        var header = $"{kindLabel} [white bold]{Markup.Escape(node.Name)}[/]";
        if (!string.IsNullOrEmpty(node.Namespace))
            header += $"\n[gray]{Markup.Escape(node.Namespace)}[/]";

        AnsiConsole.Write(new Panel(header)
        {
            Header = new PanelHeader(" describe "),
            Border = BoxBorder.Rounded,
            Padding = new Padding(1, 0)
        });
        AnsiConsole.WriteLine();

        // partial file count
        var partialCount = CountPartialFiles(t);
        if (partialCount > 1)
            AnsiConsole.MarkupLine($"[gray]partial class — merged from {partialCount} files[/]\n");

        // Inheritance
        if (node.BaseTypes.Any())
        {
            AnsiConsole.MarkupLine("[yellow]── Inheritance / Implementation[/]");
            var chain = BuildAncestorChain(node.Name, allParsed);
            if (chain.Count > 1)
            {
                var chainStr = string.Join(" → ", new[] { node.Name }.Concat(chain));
                AnsiConsole.MarkupLine($"  [purple]chain:[/] {Markup.Escape(chainStr)}");
                var extra = node.BaseTypes.Skip(1).ToList();
                if (extra.Any())
                    AnsiConsole.MarkupLine($"  [purple]also:[/] {Markup.Escape(string.Join(", ", extra))}");
            }
            else
            {
                foreach (var bt in node.BaseTypes)
                    AnsiConsole.MarkupLine($"  [purple]:[/] {Markup.Escape(bt)}");
            }
            AnsiConsole.WriteLine();
        }

        // Fields/Properties
        PrintFieldSection(t.Fields);

        // Methods
        PrintMethodSection(t.Methods);

        // External References (unique types only)
        var outRefs = t.Edges
            .Where(e => e.Kind != EdgeKind.Inheritance)
            .GroupBy(e => e.To)
            .Select(g => (type: g.Key, kinds: g.Select(e => e.Kind).Distinct().ToList(),
                members: g.Select(e => e.MemberName).Where(m => !string.IsNullOrEmpty(m))
                    .Distinct().Take(3).ToList()))
            .OrderBy(x => x.type)
            .ToList();

        if (outRefs.Any())
        {
            AnsiConsole.MarkupLine("[yellow]── External References (out-degree)[/]");
            var table = new Table().Border(TableBorder.Simple)
                .AddColumn("Type")
                .AddColumn("Kind")
                .AddColumn("Member Examples");

            foreach (var (type, kinds, members) in outRefs)
            {
                var kindStr = string.Join(", ", kinds.Select(k => k switch
                {
                    EdgeKind.Field     => "[teal]field[/]",
                    EdgeKind.Property  => "[teal]prop[/]",
                    EdgeKind.Parameter => "[gray]param[/]",
                    _                  => ""
                }));
                var memberStr = members.Any()
                    ? Markup.Escape(string.Join(", ", members))
                    : "[gray]-[/]";
                table.AddRow(Markup.Escape(type), kindStr, memberStr);
            }
            AnsiConsole.Write(table);
            AnsiConsole.WriteLine();
        }

        // Classes referring to this one (in-degree)
        if (referencedBy.Any())
        {
            AnsiConsole.MarkupLine($"[yellow]── Referenced By (in-degree: {referencedBy.Count})[/]");
            var chunks = referencedBy.Chunk(5);
            foreach (var chunk in chunks)
                AnsiConsole.MarkupLine("  " + string.Join("  [gray]·[/]  ",
                    chunk.Select(c => Markup.Escape(c))));
            AnsiConsole.WriteLine();
        }

        // Summary
        AnsiConsole.Write(new Rule("[gray]Summary[/]") { Justification = Justify.Left });
        AnsiConsole.MarkupLine(
            $"Fields/Props [white]{t.Fields.Count}[/]  |  " +
            $"Methods [white]{t.Methods.Count}[/]  |  " +
            $"External Ref Types [white]{outRefs.Count}[/]  |  " +
            $"Referenced By [white]{referencedBy.Count}[/]");
    }

    private void PrintFieldSection(List<FieldInfo> fields)
    {
        if (!fields.Any()) return;

        AnsiConsole.MarkupLine("[yellow]── Fields / Properties[/]");
        var table = new Table().Border(TableBorder.Simple)
            .AddColumn("Name")
            .AddColumn("Type")
            .AddColumn("Access")
            .AddColumn("Kind");

        var pubFields  = fields.Where(f => f.IsPublic).OrderBy(f => f.Name).ToList();
        var privFields = fields.Where(f => !f.IsPublic).OrderBy(f => f.Name).ToList();

        foreach (var f in pubFields.Concat(privFields).Take(40))
        {
            var access = f.IsPublic ? "[white]public[/]" : "[gray]private[/]";
            if (f.IsStatic)   access += " [blue]static[/]";
            if (f.IsReadOnly) access += " [gray]readonly[/]";
            var kind = f.Kind == EdgeKind.Property ? "[teal]prop[/]" : "[gray]field[/]";
            table.AddRow(Markup.Escape(f.Name), Markup.Escape(f.TypeName), access, kind);
        }

        if (fields.Count > 40)
            table.AddRow($"[gray]... and {fields.Count - 40} more[/]", "", "", "");

        AnsiConsole.Write(table);
        AnsiConsole.WriteLine();
    }

    private void PrintMethodSection(List<MethodInfo> methods)
    {
        if (!methods.Any()) return;

        AnsiConsole.MarkupLine("[yellow]── Methods[/]");
        var table = new Table().Border(TableBorder.Simple)
            .AddColumn("Name")
            .AddColumn("Return Type")
            .AddColumn("Parameters")
            .AddColumn("Modifiers");

        var pubMethods  = methods.Where(m => m.IsPublic).OrderBy(m => m.Name).ToList();
        var privMethods = methods.Where(m => !m.IsPublic).OrderBy(m => m.Name).ToList();

        foreach (var m in pubMethods.Concat(privMethods).Take(50))
        {
            var mods = new List<string>();
            if (m.IsAsync)    mods.Add("[blue]async[/]");
            if (m.IsVirtual)  mods.Add("[purple]virtual[/]");
            if (m.IsOverride) mods.Add("[purple]override[/]");
            if (m.IsStatic)   mods.Add("[gray]static[/]");
            if (!m.IsPublic)  mods.Add("[gray]private[/]");

            var paramStr = m.Parameters.Count == 0
                ? "[gray]( )[/]"
                : "(" + Markup.Escape(string.Join(", ", m.Parameters)) + ")";
            var modStr = mods.Any() ? string.Join(" ", mods) : "[white]public[/]";

            table.AddRow(Markup.Escape(m.Name), Markup.Escape(m.ReturnType), paramStr, modStr);
        }

        if (methods.Count > 50)
            table.AddRow($"[gray]... and {methods.Count - 50} more[/]", "", "", "");

        AnsiConsole.Write(table);
        AnsiConsole.WriteLine();
    }

    // ── Mermaid classDiagram 출력 ─────────────────────────────────

    private string ExportMermaid(ParsedType t, List<string> referencedBy)
    {
        var sb = new System.Text.StringBuilder();
        sb.AppendLine("classDiagram");

        var name = t.Node.Name;

        // 클래스 선언
        sb.AppendLine($"  class {name} {{");
        sb.AppendLine($"    <<{t.TypeKind}>>");

        // 필드 (public만)
        foreach (var f in t.Fields.Where(f => f.IsPublic).Take(20))
            sb.AppendLine($"    +{f.TypeName} {f.Name}");

        // 메서드 (public만)
        foreach (var m in t.Methods.Where(m => m.IsPublic).Take(30))
        {
            var prefix = m.IsAsync ? "async " : "";
            var paramStr = string.Join(", ", m.Parameters);
            sb.AppendLine($"    +{prefix}{m.ReturnType} {m.Name}({paramStr})");
        }

        sb.AppendLine("  }");
        sb.AppendLine();

        // 상속 관계
        foreach (var bt in t.Node.BaseTypes)
            sb.AppendLine($"  {bt} <|-- {name} : extends");

        // 외부 참조 (field/property)
        var outRefs = t.Edges
            .Where(e => e.Kind == EdgeKind.Field || e.Kind == EdgeKind.Property)
            .GroupBy(e => e.To)
            .Select(g => (type: g.Key, member: g.First().MemberName))
            .Take(20);

        foreach (var (type, member) in outRefs)
            sb.AppendLine($"  {name} --> {type} : {member}");

        // 참조받는 클래스
        foreach (var caller in referencedBy.Take(10))
            sb.AppendLine($"  {caller} ..> {name} : uses");

        return sb.ToString();
    }

    // ── DOT 출력 ─────────────────────────────────────────────────

    private string ExportDot(ParsedType t, List<string> referencedBy)
    {
        var sb = new System.Text.StringBuilder();
        var name = t.Node.Name;

        sb.AppendLine($"digraph {name} {{");
        sb.AppendLine("  rankdir=LR;");
        sb.AppendLine("  node [shape=record, style=filled, fontname=\"sans-serif\", fontsize=11];");
        sb.AppendLine("  edge [fontname=\"sans-serif\", fontsize=9];");
        sb.AppendLine();

        // 메인 클래스 노드 (record 형식으로 필드/메서드 포함)
        var fields = t.Fields.Where(f => f.IsPublic).Take(15)
            .Select(f => $"+ {EscDot(f.TypeName)} {EscDot(f.Name)}");
        var methods = t.Methods.Where(m => m.IsPublic).Take(20)
            .Select(m => $"+ {(m.IsAsync ? "async " : "")}{EscDot(m.ReturnType)} {EscDot(m.Name)}()");

        var members = string.Join("\\l", fields.Concat(methods));
        if (!string.IsNullOrEmpty(members)) members += "\\l";

        sb.AppendLine($"  \"{name}\" [");
        sb.AppendLine($"    label=\"{{\\<\\<{t.TypeKind}\\>\\>\\n{name}|{members}}}\",");
        sb.AppendLine($"    fillcolor=\"#E1F5EE\", color=\"#0F6E56\", fontcolor=\"#085041\"");
        sb.AppendLine("  ];");
        sb.AppendLine();

        // 상속 관계
        foreach (var bt in t.Node.BaseTypes)
        {
            sb.AppendLine($"  \"{bt}\" [fillcolor=\"#EEEDFE\", color=\"#534AB7\", fontcolor=\"#3C3489\"];");
            sb.AppendLine($"  \"{bt}\" -> \"{name}\" [style=dashed, color=\"#7F77DD\", label=\"extends\"];");
        }

        // 외부 참조 (field/property, unique)
        var outRefs = t.Edges
            .Where(e => e.Kind == EdgeKind.Field || e.Kind == EdgeKind.Property)
            .GroupBy(e => e.To)
            .Select(g => (type: g.Key, member: g.First().MemberName, count: g.Count()))
            .Take(15);

        foreach (var (type, member, _) in outRefs)
        {
            sb.AppendLine($"  \"{type}\" [fillcolor=\"#F1EFE8\", color=\"#888780\", fontcolor=\"#444441\"];");
            sb.AppendLine($"  \"{name}\" -> \"{type}\" [color=\"#1D9E75\", label=\"{EscDot(member)}\"];");
        }

        // 참조받는 클래스
        foreach (var caller in referencedBy.Take(8))
        {
            sb.AppendLine($"  \"{caller}\" [fillcolor=\"#FAEEDA\", color=\"#BA7517\", fontcolor=\"#633806\"];");
            sb.AppendLine($"  \"{caller}\" -> \"{name}\" [style=dotted, color=\"#BA7517\", label=\"uses\"];");
        }

        sb.AppendLine("}");
        return sb.ToString();
    }

    private static List<string> BuildAncestorChain(string className, List<ParsedType> allParsed, int maxDepth = 20)
    {
        var lookup = allParsed.ToDictionary(p => p.Node.Name, p => p.Node);
        var chain = new List<string>();
        var current = className;
        var visited = new HashSet<string>();
        for (int i = 0; i < maxDepth; i++)
        {
            if (visited.Contains(current)) break;
            visited.Add(current);
            if (!lookup.TryGetValue(current, out var node) || !node.BaseTypes.Any())
                break;
            chain.Add(node.BaseTypes[0]);
            current = node.BaseTypes[0];
        }
        return chain;
    }

    private int CountPartialFiles(ParsedType t)
    {
        // partial class는 파싱 시 이미 병합되어 파일 수를 별도로 추적하기 어려움
        // 편의상 1 반환 (추후 확장 가능)
        return 1;
    }

    private string EscDot(string s) =>
        s.Replace("\"", "'").Replace("<", "\\<").Replace(">", "\\>").Replace("{", "\\{").Replace("}", "\\}");
}