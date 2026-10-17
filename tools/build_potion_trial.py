"""Build a local, unpublished six-family potion trial in a NEW staging folder.

Does not read potion resources, install, execute WeiDU, launch a game or create
an archive. Production fingerprints are fixed; the CLI has no bypass option.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "research/labs/potion-default"
PROTOTYPE = ROOT / "research/prototypes/potion-admission"
MOD = "cbr_potion_trial"
SETUP = "setup-cbr_potion_trial.tp2"
MODULES = {
    "core": ("CBRPQCore", "table"), "messages": ("CBRPQMessages", "function"),
    "native": ("CBRPQNative", "function"), "runtime": ("CBRPQRuntime", "function"),
    "hook": ("CBRPQHook", "table"), "transport": ("CBRPQTransport", "table"),
    "watchdog": ("CBRPQWatchdog", "table"), "compiler": ("CBRPQCompile", "table"),
    "hash": ("CBRPQHash", "table"), "resources": ("CBRPQResources", "function"),
    "boot": ("CBRPQBoot", "table"), "lab": ("CBRPQLab", "table"),
}
# BG2EE 2.7.3.0 / EEex 1.3.0 + LuaJIT, read-only capture at
# %USERPROFILE%/Games/CBR-TimeStop-2.7.3.0. No engine/EEex binaries are bundled.
# MD5 is for WeiDU's native predicate; SHA256 is independently checked at startup.
PINNED_BINARIES = {
    "Baldur.exe": ("68d3b46a164931d2136c38aff397b4b1", "b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57"),
    "EEex.dll": ("a62081d49e890f055b5d8071362c012d", "cc06e13f3376557c6966442f5c6989d299f97c48c30999515c064373f9e9b882"),
    "InfinityLoaderDLL.dll": ("101ef44af62c4f850ad54ce26195fc5f", "cf464444352e7279cc41ce5515728343f4703722023c10fc0d35ef80768363d1"),
    "InfinityLoaderCommon.dll": ("fc5e9c92e329b58284048c1d6badaba9", "4cc6358e9efe538ad647fa734de3c25a5ebad5c4aebb9c260c18bf31b6d3f72f"),
    "InfinityLoaderUtil.dll": ("63fdb506be204aa9d5baf31ad67f08f0", "cc46b50941b9f91430bd8d7f69b62c95d8e4f51cf8c81f2f4a8d3332f507f37a"),
    "LuaBindings.dll": ("c2d70bbaea5c2b54d607c42650262367", "728465fddc091ff5d7817b3f33f4d735af51031a753ab1568490bf1a9a22348f"),
    "LuaBindingsCore.dll": ("b6c05e2a764d957e789b73dcdaa9f257", "0e5c0ce6e319b82bcb4ea4e95cb7d2a3c89273998d98f14f9b2440918a53009f"),
    "LuaProvider.dll": ("4100738d730dc93cb9b753a5d9f29b57", "fdc697e875e5c47df082b7f0a083f2d91e1b0cbabdfd777a82e228a4c8958966"),
    "lua51.dll": ("708980b26d2c8fe1eab7c094b8d984a9", "7db4318cbd119f5fac8b7993901f9147f56c55973f31f1532586266dc8d3ba30"),
}
PINNED_PROFILES = {
    "eeex-1.3.0-pinned": PINNED_BINARIES,
    "eeex-1.2.0-default-direct-trial": {
        "Baldur.exe": PINNED_BINARIES["Baldur.exe"],
        "EEex.dll": ("2208f4397ea9c13d450b2cf871f75766", "adc09b72951a28fed7b56ca1eba530f54c90505a495432f97401ea3c9b19a4c9"),
        "InfinityLoaderDLL.dll": ("a6ec58cc53caac045663fbda56ea3b29", "f5519cffd3ca12fd09e6ca055d2441602097c7dd2155fd69ff9c1708598107dd"),
        "InfinityLoaderCommon.dll": ("d98fa85afca16933c2de9c5015ddb8ae", "c930b359a3eae87805995e073c551ade5437c4300865e5f3074bbdc993337c9f"),
        "InfinityLoaderUtil.dll": ("f9edbf035caed47d72cff87435880186", "e00cc09c7b8434c9fb46e2c275746d43915d559ece0999aaf2a951b9cb9c2601"),
        "LuaBindings.dll": ("f0ff26983110aba2cbd7381e748812b7", "0c6a86dbb402aa5863286c4398cc9e691fa8a2cd7f83d517b29edcaeac51f1e9"),
        "LuaBindingsCore.dll": ("629ee156b35555c6ac99783419ca20db", "cd6993f12523012e83cf8a01a97913a47bd244fa8796d5db0811ceed47d166ca"),
        "LuaProvider.dll": ("f5b4e1d22233707c898ae3cea9584a18", "44156a5917d0e8298393d85e2181c139489159b34a53a6332414a705c50684d3"),
        "lua51.dll": PINNED_BINARIES["lua51.dll"],
    },
}


def _render_files() -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    modules = []
    for key, (name, kind) in MODULES.items():
        original = (PROTOTYPE / f"{name}.lua").read_text(encoding="utf-8")
        wrapper = ("-- LOCAL PILOT wrapper: EEex_DoFile returns no module value.\n"
                   "assert(type(CBRPQTrialModules)=='table','trial module registry missing')\n"
                   f"assert(CBRPQTrialModules.{key}==nil,'trial module slot already populated: {key}')\n"
                   "local value=(function()\n" + original + "\nend)()\n"
                   f"assert(type(value)=='{kind}','trial module did not return {kind}: {name}')\n"
                   f"CBRPQTrialModules.{key}=value\n")
        files[f"{MOD}/lua/{name}.lua"] = wrapper.encode("utf-8")
        modules.append(f'{{key="{key}",name="{name}",kind="{kind}"}}')
    hashes = ",\n".join(f'    {{name="{profile}",files={{' +
                         ",".join(f'{{name="{name}",sha256="{sha}"}}' for name, (_, sha) in sorted(entries.items())) + "}}"
                         for profile, entries in sorted(PINNED_PROFILES.items()))
    loader = (TEMPLATES / "M_CBRPQ.lua.in").read_text(encoding="utf-8")
    loader = loader.replace("@@MODULES@@", ",\n    ".join(modules)).replace("@@BINARIES@@", hashes)
    files[f"{MOD}/M_CBRPQ.lua"] = loader.encode("utf-8")
    guards = []
    for name in sorted({name for entries in PINNED_PROFILES.values() for name in entries}):
        guards.append(f'REQUIRE_PREDICATE (FILE_EXISTS ~{name}~) ~Trial prerequisite missing: {name}.~')
    coherent = " OR ".join("(" + " AND ".join(f'(FILE_MD5 ~{name}~ ~{md5}~)' for name, (md5, _) in sorted(entries.items())) + ")"
                            for entries in PINNED_PROFILES.values())
    guards.append(f'REQUIRE_PREDICATE ({coherent}) ~Trial requires one coherent pinned BG2EE 2.7.3.0 / EEex binary set; changed or mixed files are unsupported.~')
    collisions = ["override/M_CBRPQ.lua"]
    for name, _ in MODULES.values():
        collisions += [f"EEex_scripts/{name}.lua", f"EEex_scripts/override/{name}.lua"]
    collision_guards = "\n".join(f'REQUIRE_PREDICATE NOT (FILE_EXISTS ~{name}~) ~Trial namespace already exists: {name}; use a fresh disposable copy.~'
                                  for name in collisions)
    setup = (TEMPLATES / "setup-cbr_potion_trial.tp2.in").read_text(encoding="utf-8")
    components = []
    for number, other, policy, title in ((0, 1, "unique", "Unique bonuses"),
                                         (1, 0, "except_genius", "Unique bonuses except Genius")):
        components.append(f'''BEGIN ~LOCAL six-family potion pilot: {title}~ DESIGNATED {number}
REQUIRE_PREDICATE NOT (MOD_IS_INSTALLED ~{SETUP}~ {other}) ~Choose one policy; use a separate disposable copy to compare policies.~
REQUIRE_PREDICATE (GAME_IS ~bg2ee eet~) ~This local pilot requires BG2EE/EET.~
REQUIRE_PREDICATE (FILE_EXISTS ~.cbr-potion-trial~) ~Disposable-trial marker missing; do not install in the played/reference game.~
{chr(10).join(guards)}
{collision_guards}
ACTION_IF MOD_IS_INSTALLED ~{SETUP}~ {other} BEGIN FAIL ~Trial policies are mutually exclusive.~ END
OUTER_SPRINT cbr_trial_policy ~{policy}~
COPY ~{MOD}/lua~ ~EEex_scripts/override~
COPY ~{MOD}/M_CBRPQ.lua~ ~override/M_CBRPQ.lua~ EVALUATE_BUFFER
''')
    files[SETUP] = setup.replace("@@COMPONENTS@@", "\n".join(components)).encode("utf-8")
    files["README-LOCAL-TRIAL.md"] = (TEMPLATES / "README.md").read_bytes()
    files["setup-cbr_potion_trial.exe"] = (ROOT / "weidu.exe").read_bytes()
    files["WEIDU-LICENSE.txt"] = (ROOT / "WEIDU-LICENSE.txt").read_bytes()
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    manifest = {"kind": "unpublished-disposable-pilot", "families": ["POTN09", "POTN29", "POTN36", "POTN37", "POTN39", "POTN41"],
                "policies": {"0": "unique", "1": "except_genius"},
                "native_fingerprints": {profile: {name: {"md5": md5, "sha256": sha} for name, (md5, sha) in entries.items()}
                                        for profile, entries in PINNED_PROFILES.items()},
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["trial-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    return files


def build(output: Path) -> Path:
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Destination must be a NEW, nonexistent staging directory; no overwrite is permitted")
    if not output.parent.is_dir():
        raise ValueError("The staging parent directory must already exist")
    output = output.resolve()
    for parent in output.parents:
        if any((parent / name).exists() for name in ("chitin.key", "Baldur.exe", "BaldurII.exe", "InfinityLoader.exe")):
            raise ValueError(f"Destination is inside a game directory: {parent}")
    if output.is_relative_to(ROOT):
        raise ValueError("Choose staging outside the source checkout")
    files = _render_files()  # Validate/read every source before creating output.
    output.mkdir(exist_ok=False)
    for name, data in files.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(data)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new non-game staging directory")
    print(build(parser.parse_args().output))
