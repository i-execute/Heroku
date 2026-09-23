"""Module `strings` dicts: keys used in code exist; positional slots == format args."""

import ast
import pathlib
import string
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
LANGS = ("en",)
EN_PACK = {}
for _mf in (ROOT / "heroku/Modules").glob("*.py"):
    try:
        _t = ast.parse(_mf.read_text())
    except SyntaxError:
        continue
    for _n in ast.walk(_t):
        if isinstance(_n, ast.Assign) and any(
            getattr(_x, "id", "") == "strings" for _x in _n.targets
        ):
            try:
                EN_PACK[_mf.stem] = ast.literal_eval(_n.value)
            except Exception:
                pass


def positional_slots(tpl: str) -> int:
    n = 0
    for _, field, _, _ in string.Formatter().parse(tpl):
        if field is None:
            continue
        if field == "" or field.isdigit():
            n += 1
    return n


def named_fields(tpl: str) -> set:
    out = set()
    for _, field, _, _ in string.Formatter().parse(tpl):
        if field and not field.isdigit():
            out.add(field)
    return out


def dyn_keys(sl: ast.expr, section: str) -> list[str]:
    """Extract literal keys from a strings[] slice: constant, conditional
    (both branches), or f-string prefix matched against the en pack.
    Empty prefix (f"{group}_added") matches nothing — caller keys are
    unknowable statically, we skip them rather than false-positive."""
    if isinstance(sl, ast.Constant):
        return [sl.value]
    if isinstance(sl, ast.JoinedStr):
        prefix = ""
        for part in sl.values:
            if isinstance(part, ast.Constant):
                prefix += part.value
            else:
                break
        if not prefix:
            return []
        return [
            k
            for k in EN_PACK.get(section, {})
            if k.startswith(prefix) and "{" not in k
        ]
    return [n.value for n in ast.walk(sl) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def section_for(path: pathlib.Path) -> str | None:
    rel = path.relative_to(ROOT / "heroku")
    parts = rel.with_suffix("").parts
    if parts[0] == "Modules":
        return parts[-1] if len(parts) == 2 else "$" + parts[0].lower()
    if len(parts) == 2:
        return "$" + parts[-1]
    return None


def main() -> int:
    packs = {"en": EN_PACK}
    calls = {}  # (section, key) -> (pos_args, kwarg_names)
    used = set()

    for mod_file in (ROOT / "heroku").rglob("*.py"):
        if "__pycache__" in str(mod_file):
            continue
        section = section_for(mod_file)
        if not section:
            continue
        try:
            tree = ast.parse(mod_file.read_text())
        except SyntaxError:
            continue

        class V(ast.NodeVisitor):
            def visit_Call(self, node: ast.Call):
                f = node.func
                # self.strings[<anything>].format(...) — covers conditional
                # slices ("a" if x else "b") and f-strings (dynamic keys)
                if (
                    isinstance(f, ast.Attribute)
                    and f.attr == "format"
                    and isinstance(f.value, ast.Subscript)
                    and isinstance(f.value.value, ast.Attribute)
                    and f.value.value.attr == "strings"
                ):
                    pos = 0
                    kws = set()
                    for a in node.args:
                        if isinstance(a, ast.Starred):
                            pos = -1
                        else:
                            pos += 1
                    for k in node.keywords:
                        kws.add(k.arg)
                    for k in dyn_keys(f.value.slice, section):
                        prev = calls.get((section, k), (0, set()))
                        if pos > prev[0] or kws - prev[1]:
                            calls[(section, k)] = (max(prev[0], pos), prev[1] | kws)
                # self.strings["key"] (used at all)
                elif (
                    isinstance(f, ast.Subscript)
                    and isinstance(f.value, ast.Attribute)
                    and f.value.attr == "strings"
                ):
                    used.update((section, k) for k in dyn_keys(f.slice, section))
                self.generic_visit(node)

            def visit_Subscript(self, node: ast.Subscript):
                if (
                    isinstance(node.value, ast.Attribute)
                    and node.value.attr == "strings"
                ):
                    used.update((section, k) for k in dyn_keys(node.slice, section))
                self.generic_visit(node)

        V().visit(tree)

    missing = sorted(
        s for s in used if s not in calls and s[1] not in packs["en"].get(s[0], {})
    )
    bad = []
    for (section, key), (pos, kws) in sorted(calls.items()):
        for lang in LANGS:
            tpl = packs[lang].get(section, {}).get(key)
            if tpl is None:
                bad.append((section, key, pos, lang, "ABSENT"))
                continue
            if not isinstance(tpl, str):
                continue
            slots = positional_slots(tpl)
            if pos >= 0 and slots != pos:
                bad.append((section, key, pos, lang, slots))
            kw_missing = kws - named_fields(tpl)
            if kw_missing:
                bad.append((section, key, f"kw {sorted(kw_missing)}", lang, "NO-NAMED"))

    if missing:
        print(f"--- {len(missing)} keys used but absent from packs:")
        for s, k in missing:
            print(f"  {s}.{k}")
    if bad:
        print(f"--- {len(bad)} mismatches:")
        for row in sorted(set(bad)):
            print(" ", row)
        return 1
    print(f"checked {len(calls)} formatted keys + {len(used)} used keys: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
