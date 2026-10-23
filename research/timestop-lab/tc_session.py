"""Drive one session of the Time Clocks lab through its Remote Console client, case by case.

Usage, while the lab's game starts through the lab slot tool's quiet run:
  set CBR_LAB_VARIANT=timeclocks
  python -I research/timestop-lab/tc_session.py TAG --mod STATE (--fresh NAME | --save FOLDER)
                                                [--cases CASE,...] [--stop-file FILE]

TAG (letters and digits, at most 8) prefixes every console log label and capture name, and names
the driver log <lab>/cbr-timestop-output/tc-driver-TAG.jsonl. STATE is what the Time Clocks mod
must report before anything runs: "absent" (not installed) or the components Install-TimeClocks.ps1
installed: "defaults" (100 and 200) or one option on top of them ("110", "120", "210", "220",
"230"). --fresh starts a new game with the pregenerated fighter, plays Imoen's opening dialogue
and keeps the party as a lab save named NAME; --save loads such a save folder (its name in the
profile's save folder). CASES are names from CASES below; each case's captures are TAG_CASE.

The driver never starts, stops or clicks the game itself: every step is one request of rc/*.lua
through lab_rc.send, and every request checks its own precondition. A failed step stops the
session and creates --stop-file, which ends the quiet run (bg_lab_slots.py run --stop); without
it the game runs until the quiet run's time limit. The session ends with rc/quit.lua.

Timing rules (README, captures timestop_01/02 and haste_01 to haste_04): a paused probe right
after the fixtures gives the subject's periodic list counter L0; its pulse boundaries fall S ticks
after the application where (L0 + S) % 15 == 0; an action after SmallWait(N) runs N + 1 ticks
after it. ApplySpellRES and CreateCreature queued while the game is paused run at once.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_rc  # noqa: E402

REQUESTS = Path(__file__).resolve().parent / "rc"
SUBJECT, CONTROLLER = "CBRTS Subject", "Imoen"
CHARACTER = "Abdel - Fighter - Neutral Good"
TARGET = "BOUNHA02"  # Bounty Hunter: neutral, no scripts, 88 HP, magic resistance 0.
TAG = re.compile(r"^[A-Za-z0-9]{1,8}$")
# The lab's clock fixtures: what clean() waits out on the two party members.
CLOCK_SOURCES = "CBRTBUF,CBRTREG,CBRTHST,CBRTIHS,CBRTSLW,CBRTSRH,CBRTDIS,CBRTSTP,CBRTSTL"
# Lab copies of saves take folder numbers 800-899, beside the game's own (quick, auto, named).
SAVE_NUMBERS = range(800, 900)
MISSING_HP = 13  # CBRTREG heals at most 12 in a case (natively hasted), so it never caps.

_DEFAULTS = {"timeStop": True, "newEffectsRun": False, "stopActors": False, "haste": True,
             "workersOnly": False, "slow": True, "hasteExpiry": False}
# The switches tc-probe must show for each mod state (M_CBTC.lua readOptions, CBTCOPT.2DA).
MOD_STATES = {
    "absent": None,
    "defaults": _DEFAULTS,
    "110": {**_DEFAULTS, "newEffectsRun": True},
    "120": {**_DEFAULTS, "stopActors": True},
    "210": {**_DEFAULTS, "workersOnly": True},
    "220": {**_DEFAULTS, "slow": False},
    "230": {**_DEFAULTS, "hasteExpiry": True},
}


class SessionError(RuntimeError):
    pass


def stop_wait(list_counter: int, target: int) -> int:
    """SmallWait N so that a stop starts about `target` ticks after the application, 6 to 9 ticks
    after a pulse boundary (timestop_01: L0 1507, target 74 -> 73; timestop_02: 1815, 37 -> 36)."""
    starts = [s for s in range(max(2, target - 7), target + 8) if (list_counter + s) % 15 in (6, 7, 8, 9)]
    return min(starts, key=lambda s: (abs(s - target), s)) - 1


def haste_wait(list_counter: int) -> int:
    """SmallWait N so that Haste starts 7 ticks after the third native heal of CBRTREG, which
    falls 45 ticks after the second pulse boundary (haste_01: L0 1496 -> 70; haste_02: 2238 -> 78)."""
    first = next(s for s in range(1, 16) if (list_counter + s) % 15 == 0)
    return first + 15 + 45 + 7 - 1


def next_save_folder(existing: list[str], name: str) -> str:
    """The next free lab save folder "NNNNNNNNN-name" in SAVE_NUMBERS; a name is never reused."""
    if not re.fullmatch(r"[A-Za-z0-9 ]{1,40}", name):
        raise SessionError(f"Invalid save name {name!r}")
    used = set()
    for folder in existing:
        match = re.fullmatch(r"(\d{9})-(.*)", folder)
        if match:
            used.add(int(match.group(1)))
            if match.group(2).lower() == name.lower():
                raise SessionError(f"A save named {name!r} exists already: {folder}")
    free = [number for number in SAVE_NUMBERS if number not in used]
    if not free:
        raise SessionError("No free lab save folder number")
    return f"{free[0]:09d}-{name}"


def match_spots(spots: list[tuple[int, int]], creatures: list[dict]) -> list[dict]:
    """Each spot's nearest creature among the new ones, each creature used once."""
    left = list(creatures)
    out = []
    for x, y in spots:
        if not left:
            raise SessionError("Fewer new creatures than spawn spots")
        best = min(left, key=lambda c: math.hypot(c["x"] - x, c["y"] - y))
        left.remove(best)
        out.append({**best, "spot": [x, y], "off_spot": round(math.hypot(best["x"] - x, best["y"] - y))})
    return out


def fixture_rows(probe: dict) -> dict:
    """The party's tracked timed effects in a tc-probe answer, comparable across a save."""
    return {key: sorted((e["source"], e["opcode"], e["timing"], e["deadline"])
                        for e in (probe["actors"].get(key) or {}).get("timed") or [])
            for key in ("portrait0", "portrait1")}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def lab_profile() -> Path:
    """The lab's own profile, as its manifest records it (Prepare-Lab.ps1)."""
    for manifest in lab_rc.LAB.glob(".cbr-*-lab.json"):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("EngineName") == lab_rc.VARIANTS[lab_rc.VARIANT][1] and data.get("ProfileRoot"):
            return Path(data["ProfileRoot"])
    raise SessionError(f"No lab manifest with this lab's profile in {lab_rc.LAB}")


class Session:
    def __init__(self, tag: str, mod: str, profile: Path | None = None):
        if lab_rc.VARIANT != "timeclocks":
            raise SessionError("Set CBR_LAB_VARIANT=timeclocks: this driver serves the Time Clocks lab only.")
        if not TAG.match(tag):
            raise SessionError("TAG: 1 to 8 letters or digits.")
        if mod not in MOD_STATES:
            raise SessionError(f"Unknown mod state {mod!r}")
        self.tag, self.mod, self.count = tag, mod, 0
        self.output = lab_rc.LAB / "cbr-timestop-output"
        self.saves = (profile or lab_profile()) / "save"
        self.output.mkdir(parents=True, exist_ok=True)
        self.log_file = (self.output / f"tc-driver-{tag}.jsonl").open("x", encoding="utf-8")
        self.subject_id = self.controller_id = None
        self.position = (0, 0)
        self.home = None  # Imoen's place when the party was ready; clean() walks her back to it
        self.loaded = None
        # Seams for the offline tests.
        self.send, self.collect, self.processes, self.sleep = lab_rc.send, lab_rc.collect, lab_rc.processes, time.sleep
        self.echo = True

    # ------------------------------------------------------------------ plumbing
    def note(self, kind: str, **data) -> None:
        self.log_file.write(json.dumps({"utc": utc(), "k": kind, **data}, ensure_ascii=False) + "\n")
        self.log_file.flush()
        if self.echo:
            print(f"[{self.tag}] {kind}: " + json.dumps(data, ensure_ascii=False)[:300], flush=True)

    def rc(self, request: str, label: str | None = None, timeout: float = 15, expect: str = "ok", **arguments):
        """One request; returns its first return value (the whole response for another status)."""
        self.count += 1
        name = f"{self.tag}-{self.count:03d}-{label or request}"
        if not lab_rc.LABEL.match(name):
            raise SessionError(f"Label not usable: {name!r}")
        path = REQUESTS / f"{request}.lua"
        code = path.read_text(encoding="utf-8")
        if arguments:
            code = lab_rc.with_arguments(code, {key: str(value) for key, value in arguments.items()})
        response = self.send(name, code, str(path), timeout, 0, expect_exit=expect == "exited")["response"]
        if response.get("status") == "timeout":
            response = self.late(name, response)
        status = response.get("status")
        if status != expect:
            self.note("failed", request=request, label=name, response=response)
            raise SessionError(f"{name}: {status}: {response.get('error') or response}")
        if status == "ok":
            return (response.get("returnValues") or [None])[0]
        return response

    def late(self, name: str, first: dict, tries: int = 8, timeout: float = 30) -> dict:
        """A request the console did not answer in time (a cutscene, a load): wait for that one."""
        for attempt in range(tries):
            response = self.collect(f"{name}-late{attempt}", timeout)["response"]
            if response.get("status") != "timeout":
                return response
        return first

    def menus(self, label: str = "menus", timeout: float = 15) -> dict:
        return self.rc("menus", label, timeout)

    @staticmethod
    def on(menus: dict, name: str) -> bool:
        return name in str(menus.get("stack", "")).split(" > ")

    def await_menu(self, test, what: str, tries: int = 20, pause: float = 0.5, timeout: float = 15) -> dict:
        state = {}
        for attempt in range(tries):
            state = self.menus(f"await-{what}-{attempt}", timeout)
            if test(state):
                return state
            self.sleep(pause)
        raise SessionError(f"Menu never reached: {what} (last: {state.get('stack')})")

    def click(self, item: str, menu: str, top: str | None, then, what: str) -> dict:
        arguments = {"item": item, "menu": menu}
        if top:
            arguments["top"] = top
        self.rc("click", what, **arguments)
        return self.await_menu(then, what)

    def pause(self, want: str, label: str | None = None) -> dict:
        return self.rc("pause", label or want, want=want)

    def run(self, ticks: int, label: str = "run") -> tuple[int, int]:
        """Unpause until the world time advanced `ticks`, then pause. A pause the game takes by
        itself (autopause) is noted and ended; the world time must keep moving."""
        state = self.pause("running", f"{label}-go")
        start = seen = state["before"]["game_time"]
        stalls = 0
        while seen - start < ticks:
            self.sleep(min(2.0, max(0.3, (ticks - (seen - start)) / 15 - 0.8)))
            state = self.pause("running", f"{label}-on")
            if state["toggled"]:
                self.note("autopause", label=label, game_time=state["before"]["game_time"])
            now = state["after"]["game_time"]
            stalls = stalls + 1 if now <= seen else 0
            if stalls >= 10:
                raise SessionError(f"{label}: the world time stands still at {now}")
            seen = max(seen, now)
        end = self.pause("paused", f"{label}-stop")["after"]["game_time"]
        return start, end

    # ------------------------------------------------------------------ setup
    def wait_for_game(self, timeout: float = 300) -> None:
        """This lab's one Baldur.exe, and a console ready file written after it started."""
        ready = lab_rc.OVERRIDE / "eeex_remote_ready.json"
        deadline = time.time() + timeout
        while time.time() < deadline:
            games = [p for p in self.processes() if p["ours"] and p["Name"].lower() == "baldur.exe"]
            if len(games) > 1:
                raise SessionError(f"More than one game runs from this lab: {games}")
            if games and ready.exists():
                started = datetime.fromisoformat(str(games[0]["CreationDate"])).timestamp()
                try:
                    stamp = str(json.loads(ready.read_text(encoding="utf-8")).get("timestamp", ""))
                    written = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
                except (OSError, ValueError):
                    stamp, written = "", 0.0
                if written >= math.floor(started) - 1:
                    self.note("game", process=games[0], ready=stamp)
                    return
            self.sleep(2)
        raise SessionError("The lab's game never came up with a fresh console ready file.")

    def startup(self) -> None:
        self.wait_for_game()
        self.rc("ping", timeout=60)
        watchdog = self.rc("watchdog", expect="error")
        if "watchdog" not in str(watchdog.get("error", "")):
            raise SessionError(f"Unexpected watchdog answer: {watchdog}")
        self.rc("ping")
        state = self.rc("state")
        if (state.get("lab_id") != lab_rc.LAB_ID.decode("ascii") or not state.get("eeex_active")
                or not state.get("at_start_engine")):
            raise SessionError(f"Unexpected start state: {state}")
        probe = self.rc("tc-probe")
        self.note("mod", expected=self.mod, time_clocks=probe.get("time_clocks"))
        self.check_mod(probe.get("time_clocks"))
        self.note("observer", install=self.rc("install"), status=self.rc("status"))
        self.rc("sampler", "sampler-install", on="0")

    def check_mod(self, clocks) -> None:
        want = MOD_STATES[self.mod]
        if want is None:
            if clocks != "not loaded":
                raise SessionError(f"The Time Clocks mod should be absent: {clocks}")
            return
        if not isinstance(clocks, dict) or clocks.get("installed") is not True \
                or not str(clocks.get("status", "")).startswith("active: "):
            raise SessionError(f"The Time Clocks mod is not active: {clocks}")
        options = clocks.get("options") or {}
        differ = {key: options.get(key) for key, value in want.items() if options.get(key) is not value}
        if differ:
            raise SessionError(f"The mod's switches differ from {self.mod!r}: {differ}")

    def to_single_player(self) -> None:
        self.await_menu(lambda m: m.get("top") == "START" and not m.get("transition"), "start")
        self.rc("start-soa")
        self.await_menu(lambda m: self.on(m, "START_MAIN"), "start-main")
        self.click("CBRTSQA_SINGLE", "START_MAIN", None, lambda m: m.get("top") == "START_SP", "single")

    def fresh_party(self, save_name: str) -> None:
        self.to_single_player()
        self.click("CBRTSQA_NEW_GAME", "START_SP", "START_SP", lambda m: m.get("top") == "CHARGEN", "new-game")
        self.click("CBRTSQA_CG_IMPORT", "CHARGEN", "CHARGEN", lambda m: m.get("top") == "POPUP_THREEBUTTON", "import")
        self.click("CBRTSQA_POPUP3_MID", "POPUP_THREEBUTTON", "POPUP_THREEBUTTON",
                   lambda m: self.on(m, "CHARACTER_SELECT"), "charfile")
        self.rc("pick-character", "pick", character=CHARACTER)
        self.await_menu(lambda m: m.get("top") == "CHARGEN", "chargen-picked")
        self.click("CBRTSQA_CG_APPEARANCE", "CHARGEN", "CHARGEN", lambda m: m.get("top") == "CHARACTER_COLOR",
                   "appearance")
        self.click("CBRTSQA_COLOR_DONE", "CHARACTER_COLOR", "CHARACTER_COLOR",
                   lambda m: m.get("top") == "CHARGEN_CUSTOMSOUNDS", "colors")
        self.click("CBRTSQA_SOUNDS_DONE", "CHARGEN_CUSTOMSOUNDS", "CHARGEN_CUSTOMSOUNDS",
                   lambda m: m.get("top") == "CHARGEN", "sounds")
        self.click("CBRTSQA_CG_NAME", "CHARGEN", "CHARGEN", lambda m: self.on(m, "CHARGEN_NAME"), "name")
        self.rc("set-name", "set-name", name=SUBJECT)
        self.await_menu(lambda m: m.get("top") == "CHARGEN" and (m.get("chargen") or {}).get("complete") is True,
                        "named")
        self.click("CBRTSQA_CG_ACCEPT", "CHARGEN", "CHARGEN", lambda m: m.get("top") == "CHARGEN_DIFFICULTY", "accept")
        self.rc("click", "venture", item="CBRTSQA_DIFF_VENTURE", menu="CHARGEN_DIFFICULTY", top="CHARGEN_DIFFICULTY")
        # The SoA opening: the console stays deaf until its cutscene ends (85 s in the Time Stop lab).
        self.await_menu(lambda m: m.get("game_loaded") == 1 and self.on(m, "WORLD_DIALOG"), "opening",
                        tries=12, pause=1, timeout=120)
        self.rc("dialog", "confirm-on", mode="confirm-on")
        for step in range(1, 21):
            if not self.on(self.menus(f"dialog-{step}"), "WORLD_DIALOG"):
                break
            self.rc("dialog", f"step-{step}", mode="step", row="1")
            self.sleep(0.5)
        else:
            raise SessionError("Imoen's dialogue did not end within 20 steps.")
        self.pause("paused")
        self.rc("dialog", "confirm-off", mode="confirm-off")
        self.party_ready()
        self.clean()
        self.keep_save(save_name, self.quicksave("base"))

    def load_save(self, folder: str) -> None:
        if not (self.saves / folder / "BALDUR.GAM").is_file():
            raise SessionError(f"No such save: {self.saves / folder}")
        self.to_single_player()
        self.click("CBRTSQA_LOAD_GAME", "START_SP", "START_SP", lambda m: self.on(m, "LOAD"), "load-game")
        self.note("saves", saves=self.rc("load-save", "saves").get("saves"))
        self.rc("load-save", "load", file=folder)
        self.await_menu(lambda m: m.get("game_loaded") == 1 and self.on(m, "WORLD_ACTIONBAR")
                        and not m.get("transition"), "loaded", tries=30, pause=1, timeout=60)
        self.pause("paused")
        self.party_ready()

    def party_ready(self) -> None:
        self.note("party-ai", **self.rc("party-ai", want="off"))
        probe = self.rc("tc-probe", "party")
        subject, controller = probe["actors"].get("portrait0"), probe["actors"].get("portrait1")
        if not subject or subject["name"] != SUBJECT or not controller or controller["name"] != CONTROLLER:
            raise SessionError(f"Unexpected party: {probe['actors']}")
        self.subject_id, self.controller_id = subject["id"], controller["id"]
        self.home = (controller["x"], controller["y"])
        self.note("party", subject=subject, controller=controller, area=probe.get("area"),
                  nearby=self.rc("nearby", range="2000"))
        self.rc("sampler", "sampler-party", ids=self.party_ids(), on="1")

    def party_ids(self, *more: int) -> str:
        return ",".join(str(i) for i in (self.subject_id, self.controller_id, *more))

    # ------------------------------------------------------------------ case helpers
    def subject(self, label: str = "subject") -> dict:
        return self.rc("subject", label)["portrait0"]

    def probe(self, label: str = "probe", ids: str = "", sources: str = "") -> dict:
        arguments = {key: value for key, value in (("ids", ids), ("sources", sources)) if value}
        return self.rc("tc-probe", label, **arguments)

    def tcq(self, actor: str, name: str, steps: str, label: str = "tcq", **extra) -> dict:
        return self.rc("tc-queue", label, actor=actor, name=name, steps=steps, **extra)

    def clean(self, missing: int = MISSING_HP) -> None:
        """Disarmed: run until no clock fixture is left on the party, no stop runs and no tracked
        projectile flies, walk Imoen back to her place, then bring the subject to `missing`
        missing HP."""
        for attempt in range(8):
            probe = self.probe(f"clean-{attempt}", sources=CLOCK_SOURCES)
            now = probe["game_time"]
            left = [effect["deadline"] - now for key in ("portrait0", "portrait1")
                    for effect in (probe["actors"].get(key) or {}).get("timed") or []]
            if probe["time_stop_remaining"]:
                left.append(probe["time_stop_remaining"] // 2 + 1)
            sampler = probe.get("sampler")
            flying = sampler.get("projectiles", 0) + sampler.get("pending", 0) if isinstance(sampler, dict) else 0
            if not left and not flying:
                break
            self.run(min(900, max([150] + [t + 15 for t in left])), f"clean{attempt}")
        else:
            raise SessionError("The lab effects or projectiles did not end.")
        # An attack case leaves Imoen beside its target; casting from there could put her inside
        # the next case's cloud.
        for attempt in range(4) if self.home else ():
            imoen = probe["actors"].get("portrait1") or {}
            if math.hypot(imoen.get("x", 0) - self.home[0], imoen.get("y", 0) - self.home[1]) <= 16:
                break
            if attempt == 3:
                raise SessionError(f"Imoen did not walk back to her place {self.home}: {imoen}")
            self.tcq("p1", CONTROLLER, f"move:{self.home[0]}:{self.home[1]}", f"home{attempt}", idle="1")
            self.run(60, f"home{attempt}")
            probe = self.probe(f"home-{attempt}")
        for attempt in range(4):
            subject = self.subject(f"hp-{attempt}")
            gap = subject["max_hp"] - subject["hp"]
            if gap >= missing:
                return
            self.rc("queue", f"damage-{attempt}", subject=SUBJECT, what="damage", amount=min(50, missing + 8 - gap))
            self.run(15, f"hurt{attempt}")
        raise SessionError("Could not lower the subject's HP.")

    def case(self, name: str, setup, ticks: int, observer: bool = True, clean: bool = True) -> dict:
        """One capture: clean, sampler on, arm, `setup` (paused), run, probe, stop and export.
        `setup` returns the case's plan; its "ids" (sampler) and "probe_ids" (tc-probe) add
        creatures, and its "ticks" replaces `ticks`."""
        capture = f"{self.tag}_{name}"
        if clean:
            self.clean()
        self.rc("sampler-export", f"{name}-flush", name=f"{capture}_pre")  # what came before
        self.rc("sampler", f"{name}-sampler", ids=self.party_ids(), on="1")
        if observer:
            self.rc("arm", f"{name}-arm")
        before = self.probe(f"{name}-p0")
        plan = setup() or {}
        if plan.get("ids"):
            self.rc("sampler", f"{name}-ids", ids=plan["ids"], on="1")
        after_setup = self.probe(f"{name}-p1", ids=plan.get("probe_ids", ""))
        start, end = self.run(plan.pop("ticks", ticks), name)
        final = self.probe(f"{name}-p2", ids=plan.get("probe_ids", ""))
        result = {"case": name, "capture": capture, "plan": plan, "start": start, "end": end,
                  "probe_before": before, "probe_setup": after_setup, "probe_after": final}
        if observer:
            result["stop"] = self.rc("stop", f"{name}-stop")
            result["export"] = self.rc("export", f"{name}-export", name=capture)
        result["samples"] = self.rc("sampler-export", f"{name}-samples", name=capture)
        self.note("case", **result)
        return result

    def fixtures(self) -> int:
        """The Time Stop lab's fixtures (CBRTBUF, CBRTREG) on the subject; returns its list counter."""
        self.rc("queue", "fixtures", subject=SUBJECT, what="fixtures")
        return self.subject("after-fixtures")["clocks"]["list"]

    def quick_saves(self) -> dict:
        if not self.saves.is_dir():
            return {}
        return {p.name: (p / "BALDUR.GAM").stat().st_mtime for p in self.saves.iterdir()
                if p.is_dir() and "quick-save" in p.name.lower() and (p / "BALDUR.GAM").is_file()}

    def quicksave(self, label: str) -> dict:
        """The stock quick save; returns its folder once the game has written it."""
        before = self.quick_saves()
        probe = self.probe(f"{label}-probe", sources=CLOCK_SOURCES)
        clicked = self.rc("save", f"{label}-save")
        for _ in range(40):
            self.sleep(1)
            now = self.quick_saves()
            changed = [name for name, mtime in now.items() if before.get(name) != mtime]
            if changed:
                self.sleep(3)  # the game writes the folder's other files around BALDUR.GAM
                record = {"label": label, "folder": max(changed, key=lambda n: now[n]), "probe": probe,
                          "clicked": clicked}
                self.note("saved", **record)
                return record
        record = {"label": label, "folder": None, "probe": probe, "clicked": clicked,
                  "menus": self.menus(f"{label}-menus")}
        self.note("save-refused", **record)
        return record

    def keep_save(self, name: str, saved: dict) -> str | None:
        """Copy a quick save to a named lab save folder, with the probe at saving beside the
        captures (cbr-timestop-output/saves/FOLDER.json)."""
        if not saved.get("folder"):
            return None
        target = next_save_folder([p.name for p in self.saves.iterdir()], name)
        shutil.copytree(self.saves / saved["folder"], self.saves / target)
        sidecar = self.output / "saves" / f"{target}.json"
        sidecar.parent.mkdir(exist_ok=True)
        with sidecar.open("x", encoding="utf-8") as handle:
            json.dump({"session": self.tag, "mod": self.mod, "utc": utc(), "quick_save": saved["folder"],
                       "label": saved["label"], "probe": saved["probe"]}, handle, indent=1)
        self.note("kept-save", folder=target, sidecar=str(sidecar))
        return target

    def quit(self) -> None:
        self.rc("quit", expect="exited", timeout=60)
        self.note("quit")

    def spawn(self, spots: list[tuple[int, int]], label: str) -> list[dict]:
        """Imoen creates one Bounty Hunter at each spot; returns them, matched to their spots."""
        known = {c["id"] for c in self.rc("nearby", f"{label}-known", range="2500")["creatures"]}
        self.tcq("p1", CONTROLLER, ";".join(f"spawn:{TARGET}:{x}:{y}" for x, y in spots), f"{label}-spawn")
        for attempt in range(4):
            new = [c for c in self.rc("nearby", f"{label}-new{attempt}", range="2500")["creatures"]
                   if c["id"] not in known]
            if len(new) >= len(spots):
                break
            self.run(8, f"{label}-appear{attempt}")
        else:
            raise SessionError(f"{label}: the targets did not appear")
        targets = match_spots(spots, new)
        self.note("targets", label=label, targets=targets)
        return targets

    def remove(self, targets: list[dict], label: str) -> None:
        """Each target leaves the game (DestroySelf), so that no later case's spell hits it, it
        never acts on a later case, and no hostile creature blocks a save."""
        for number, target in enumerate(targets, 1):
            self.tcq(str(target["id"]), target["name"], "destroy", f"{label}-destroy{number}")
        ids = {target["id"] for target in targets}
        for attempt in range(4):
            self.run(8, f"{label}-leave{attempt}")
            left = [c["id"] for c in self.rc("nearby", f"{label}-left{attempt}", range="2500")["creatures"]
                    if c["id"] in ids and c.get("hp", 1) > 0]
            if not left:
                self.note("removed", label=label, targets=sorted(ids))
                return
        raise SessionError(f"{label}: the targets {left} did not leave")


# ---------------------------------------------------------------------- clock cases
def case_base(s: Session, name: str) -> dict:
    return s.case(name, lambda: {"L0": s.fixtures()}, 300)


def case_stop(s: Session, name: str, target: int) -> dict:
    def setup():
        l0 = s.fixtures()
        wait = stop_wait(l0, target)
        s.rc("queue", "timestop", subject=SUBJECT, what="timestop", controller=CONTROLLER, wait=wait)
        return {"L0": l0, "target": target, "wait": wait, "stop_at": wait + 1}
    return s.case(name, setup, 330)


def case_stop_new(s: Session, name: str) -> dict:
    """CBRTBUF reaches the frozen subject 20 ticks into the stop (choice 2: it waits for the end)."""
    def setup():
        s.tcq("p0", SUBJECT, "apply:CBRTREG:self", "regen", idle="1", nostop="1")
        l0 = s.subject("after-regen")["clocks"]["list"]
        wait = stop_wait(l0, 37)
        s.tcq("p1", CONTROLLER, f"wait:{wait};mark:stop_cast;apply:CBRTSTP:self;wait:20;mark:buff_in_stop;"
              "apply:CBRTBUF:p0", "stop-then-buff", idle="1", nostop="1")
        return {"L0": l0, "wait": wait, "stop_at": wait + 1, "buff_at": wait + 22}
    return s.case(name, setup, 360)


def case_caster(s: Session, name: str) -> dict:
    """The caster's own CBRTBUF runs on (choice 3); the frozen subject's waits."""
    def setup():
        l0 = s.fixtures()
        s.tcq("p1", CONTROLLER, "apply:CBRTBUF:self", "caster-buff", idle="1", nostop="1")
        wait = stop_wait(l0, 37)
        s.tcq("p1", CONTROLLER, f"wait:{wait};mark:stop_cast;apply:CBRTSTP:self", "caster-stop", idle="1")
        return {"L0": l0, "wait": wait, "stop_at": wait + 1}
    return s.case(name, setup, 330)


def case_haste_in(s: Session, name: str, spell: str) -> dict:
    def setup():
        l0 = s.fixtures()
        wait = haste_wait(l0)
        s.rc("queue", "haste", subject=SUBJECT, what="haste", spell=spell, wait=wait)
        return {"L0": l0, "spell": spell, "wait": wait, "haste_at": wait + 1}
    return s.case(name, setup, 315)


def case_haste_out(s: Session, name: str) -> dict:
    """Hasted for about 14 s, then the fixtures; Haste ends 6 s later (as haste_03)."""
    def setup():
        s.rc("queue", "haste", subject=SUBJECT, what="haste", spell="CBRTHST", wait=0)
        hasted = s.run(210, f"{name}-hasted")
        return {"hasted": hasted, "L0": s.fixtures()}
    return s.case(name, setup, 300)


def case_with(s: Session, name: str, spells: list[str]) -> dict:
    """The fixtures, then more lab spells on the subject at the same tick (Slow, SR's Haste, ...)."""
    def setup():
        l0 = s.fixtures()
        s.tcq("p0", SUBJECT, ";".join(f"apply:{spell}:self" for spell in spells), "-".join(spells).lower())
        return {"L0": l0, "spells": spells}
    return s.case(name, setup, 315)


def case_disease(s: Session, name: str, spells: list[str]) -> dict:
    """CBRTDIS (2 HP each second for 8 s), alone or with more lab spells at the same tick, without
    the regeneration fixture: every HP change of the subject is a disease pulse."""
    def setup():
        s.tcq("p0", SUBJECT, ";".join(f"apply:{spell}:self" for spell in spells), "-".join(spells).lower())
        return {"spells": spells, "L0": s.subject("after-disease")["clocks"]["list"]}
    return s.case(name, setup, 180)


def case_save(s: Session, name: str, target: int, after_start: int, keep: str) -> dict:
    """A stop that starts `target` ticks after the fixtures; `after_start` ticks after the
    application the game is saved (and the save kept as `keep`), then runs on until both end."""
    def setup():
        l0 = s.fixtures()
        wait = stop_wait(l0, target)
        s.rc("queue", "timestop", subject=SUBJECT, what="timestop", controller=CONTROLLER, wait=wait)
        ran = s.run(after_start, f"{name}-before-save")
        saved = s.quicksave(name)
        return {"L0": l0, "wait": wait, "stop_at": wait + 1, "ran": ran, "saved": saved,
                "kept": s.keep_save(keep, saved)}
    return s.case(name, setup, 300)


def case_load(s: Session, name: str) -> dict:
    """Right after loading: world time and the party's clock fixtures as when the save was made
    (its sidecar), then they run out."""
    if not s.loaded:
        raise SessionError("The load case needs --save.")
    saved = json.loads((s.output / "saves" / f"{s.loaded}.json").read_text(encoding="utf-8"))["probe"]

    def setup():
        now = s.probe(f"{name}-loaded", sources=CLOCK_SOURCES)
        check = {"folder": s.loaded, "game_time": [saved["game_time"], now["game_time"]],
                 "fixtures_equal": fixture_rows(saved) == fixture_rows(now), "saved": fixture_rows(saved),
                 "loaded": fixture_rows(now), "time_stop_saved": saved["time_stop_remaining"],
                 "time_stop_loaded": now["time_stop_remaining"]}
        s.note("load-check", **check)
        left = [e["deadline"] - now["game_time"] for e in (now["actors"].get("portrait0") or {}).get("timed") or []]
        return {"check": check, "ticks": max([150] + [t + 45 for t in left])}
    return s.case(name, setup, 300, clean=False)


# ---------------------------------------------------------------------- area cases
# Every area case spawns its own Bounty Hunters (neutral, no scripts): about 400 px west of the
# subject (cloud and fireball targets) or beside Imoen (melee), and removes them afterwards.
# Imoen, the stop's caster, casts with ReallyForceSpell(Point)RES; CBRTSTL stops time for 15 s.
# Before she attacks, her target turns hostile (without scripts it still never acts): in session
# n2 her AttackOneRound against neutral targets never hit. She attacks for two rounds, both within
# the stop: in sessions n3 and n4 her first AttackOneRound hit only once in four (n3's case F),
# although with CBRTHIT only a natural 1 misses; both of n4's second rounds hit within 17 ticks.
# The sampler records each projectile from its decode to its end, and the targets' HP and
# tracked effects.
def _west(s: Session) -> list[tuple[int, int]]:
    x, y = s.position
    return [(x - 400, y - 30), (x - 400, y + 70)]


def _near(s: Session) -> list[tuple[int, int]]:
    x, y = s.position
    return [(x - 70, y + 75)]


def _targets(s: Session, spots, label: str, saves: bool = False) -> list[dict]:
    targets = s.spawn(spots, label)
    if saves:
        keys = {f"t{i + 1}": t["id"] for i, t in enumerate(targets)}
        s.tcq("p1", CONTROLLER, ";".join(f"apply:CBRTSAV:{key}" for key in keys), f"{label}-saves", **keys)
    return targets


def _ids(s: Session, targets: list[dict]) -> dict:
    extra = [t["id"] for t in targets]
    return {"targets": targets, "ids": s.party_ids(*extra), "probe_ids": ",".join(str(i) for i in extra)}


def _area(s: Session, name: str, setup, ticks: int) -> dict:
    """An area case without the observer; its targets leave the game afterwards."""
    result = s.case(name, setup, ticks, observer=False)
    s.remove(result["plan"]["targets"], name)
    return result


def area_existing_clouds(s: Session, name: str) -> dict:
    """A: a target's Stinking Cloud and Imoen's Cloudkill exist when the stop begins."""
    def setup():
        t1, t2 = _targets(s, _west(s), name, saves=True)
        s.tcq(str(t1["id"]), t1["name"], f"mark:a_target_cloud;castpoint:SPWI213:{t1['x']}:{t1['y']}",
              f"{name}-t1-cloud")
        s.tcq("p1", CONTROLLER, f"mark:a_caster_cloud;castpoint:SPWI502:{t2['x']}:{t2['y']};wait:45;mark:a_stop;"
              "apply:CBRTSTL:self", f"{name}-cloud-stop")
        return _ids(s, [t1, t2])
    return _area(s, name, setup, 480)


def area_new_cloud(s: Session, name: str) -> dict:
    """B: Imoen casts Stinking Cloud 15 ticks into the stop."""
    def setup():
        (t1,) = _targets(s, _west(s)[:1], name, saves=True)
        s.tcq("p1", CONTROLLER, f"wait:5;mark:b_stop;apply:CBRTSTL:self;wait:15;mark:b_cast;"
              f"castpoint:SPWI213:{t1['x']}:{t1['y']}", f"{name}-stop-cloud")
        return _ids(s, [t1])
    return _area(s, name, setup, 450)


def area_missiles(s: Session, name: str) -> dict:
    """C: Magic Missile and Fireball cast 10 ticks into the stop; their impacts against its end."""
    def setup():
        t1, t2 = _targets(s, _west(s), name)
        s.tcq("p1", CONTROLLER, "wait:5;mark:c_stop;apply:CBRTSTL:self;wait:10;mark:c_missile;cast:SPWI112:t1;"
              "mark:c_fireball;cast:SPWI304:t2", f"{name}-stop-cast", t1=t1["id"], t2=t2["id"])
        return _ids(s, [t1, t2])
    return _area(s, name, setup, 420)


def area_missile_in_flight(s: Session, name: str) -> dict:
    """C2: Fireball cast 3 ticks before a 6 s stop begins, so it flies when the stop begins."""
    def setup():
        (t1,) = _targets(s, _west(s)[:1], name)
        s.tcq("p1", CONTROLLER, "mark:c2_fireball;cast:SPWI304:t1;wait:2;mark:c2_stop;apply:CBRTSTP:self",
              f"{name}-cast-stop", t1=t1["id"])
        return _ids(s, [t1])
    return _area(s, name, setup, 300)


def area_traps(s: Session, name: str) -> dict:
    """D: Delayed Blast Fireball and Skull Trap cast 10 ticks into the stop."""
    def setup():
        t1, t2 = _targets(s, _west(s), name)
        s.tcq("p1", CONTROLLER, f"wait:5;mark:d_stop;apply:CBRTSTL:self;wait:10;mark:d_dbf;"
              f"castpoint:SPWI712:{t1['x']}:{t1['y']};mark:d_skull;castpoint:SPWI313:{t2['x']}:{t2['y']}",
              f"{name}-stop-traps")
        return _ids(s, [t1, t2])
    return _area(s, name, setup, 480)


def area_contingency(s: Session, name: str) -> dict:
    """E: Imoen hits a frozen target whose contingency casts Magic Missile at whoever hits it."""
    def setup():
        (t1,) = _targets(s, _near(s), name)
        s.tcq("p1", CONTROLLER, "apply:CBRTHIT:self;apply:CBRTCON:t1", f"{name}-prepare", t1=t1["id"])
        s.tcq("p1", CONTROLLER, "wait:5;mark:e_stop;apply:CBRTSTL:self;wait:10;mark:e_attack;hostile:t1;attack:t1;"
              "mark:e_attack2;attack:t1", f"{name}-stop-attack", t1=t1["id"])
        return _ids(s, [t1])
    return _area(s, name, setup, 420)


def area_instant(s: Session, name: str) -> dict:
    """F: CBRTDMG (the instant projectile) and two melee rounds against a frozen target."""
    def setup():
        (t1,) = _targets(s, _near(s), name)
        s.tcq("p1", CONTROLLER, "apply:CBRTHIT:self;wait:5;mark:f_stop;apply:CBRTSTL:self;wait:10;mark:f_damage;"
              "cast:CBRTDMG:t1;mark:f_attack;hostile:t1;attack:t1;mark:f_attack2;attack:t1", f"{name}-stop-hit",
              t1=t1["id"])
        return _ids(s, [t1])
    return _area(s, name, setup, 330)


def area_sr_cloud(s: Session, name: str) -> dict:
    """G: Spell Revisions' Cloudkill (its own projectile DVCKILL, staged as CBRTSRCK) exists when
    the stop begins, as Imoen's Cloudkill in case A."""
    if not (lab_rc.OVERRIDE / "CBRTSRCK.SPL").is_file():
        raise SessionError("Stage Spell Revisions' Cloudkill first (Stage-Diagnostics.ps1 -SpellRevisionsRoot).")

    def setup():
        (t1,) = _targets(s, _west(s)[:1], name)
        s.tcq("p1", CONTROLLER, f"mark:g_cloud;castpoint:CBRTSRCK:{t1['x']}:{t1['y']};wait:45;mark:g_stop;"
              "apply:CBRTSTL:self", f"{name}-cloud-stop")
        return _ids(s, [t1])
    return _area(s, name, setup, 480)


CASES = {
    "base": case_base,
    "stop74": lambda s, n: case_stop(s, n, 74),
    "stop37": lambda s, n: case_stop(s, n, 37),
    "stopnew": case_stop_new,
    "caster": case_caster,
    "haste": lambda s, n: case_haste_in(s, n, "CBRTHST"),
    "ihaste": lambda s, n: case_haste_in(s, n, "CBRTIHS"),
    "hasteout": case_haste_out,
    "slow": lambda s, n: case_with(s, n, ["CBRTSLW"]),
    "srhaste": lambda s, n: case_with(s, n, ["CBRTSRH"]),
    "dis": lambda s, n: case_disease(s, n, ["CBRTDIS"]),
    "hastedis": lambda s, n: case_disease(s, n, ["CBRTDIS", "CBRTHST"]),
    # A save 50 ticks after a 90-tick stop that began 30 ticks after the fixtures, and one in the
    # middle of a stop; the load case checks either in a new process.
    "save": lambda s, n: case_save(s, n, 30, 170, f"CBTC {s.tag} after stop"),
    "savestop": lambda s, n: case_save(s, n, 20, 75, f"CBTC {s.tag} in stop"),
    "load": case_load,
    "areaa": area_existing_clouds,
    "areab": area_new_cloud,
    "areac": area_missiles,
    "areac2": area_missile_in_flight,
    "aread": area_traps,
    "areae": area_contingency,
    "areaf": area_instant,
    "areag": area_sr_cloud,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tag")
    parser.add_argument("--mod", required=True, choices=sorted(MOD_STATES))
    start = parser.add_mutually_exclusive_group(required=True)
    start.add_argument("--fresh", metavar="NAME", help="a new party, kept as the lab save NAME")
    start.add_argument("--save", metavar="FOLDER", help="load this save folder")
    parser.add_argument("--cases", default="", help="comma-separated names from CASES")
    parser.add_argument("--stop-file", type=Path, help="created when the session stops early")
    args = parser.parse_args(argv)
    cases = [name for name in args.cases.split(",") if name]
    unknown = [name for name in cases if name not in CASES]
    if unknown or len(set(cases)) != len(cases):
        parser.error(f"unknown or repeated cases: {unknown or cases}")
    if "load" in cases and not args.save:
        parser.error("the load case needs --save")
    if args.stop_file and args.stop_file.exists():
        parser.error(f"the stop file exists already: {args.stop_file}")
    session = Session(args.tag, args.mod)
    session.loaded = args.save
    finished = False
    try:
        session.note("plan", mod=args.mod, fresh=args.fresh, save=args.save, cases=cases)
        session.startup()
        if args.fresh:
            session.fresh_party(args.fresh)
        else:
            session.load_save(args.save)
        for name in cases:
            subject = session.subject(f"{name}-where")
            session.position = (subject["x"], subject["y"])
            CASES[name](session, name)
        session.quit()
        finished = True
    except (SessionError, lab_rc.ClientError, OSError, ValueError, KeyError, TypeError) as error:
        session.note("stopped", error=f"{type(error).__name__}: {error}")
        print(f"TC_SESSION_ERROR: {error}", file=sys.stderr)
    finally:
        if not finished and args.stop_file:
            args.stop_file.write_text(f"{session.tag} stopped {utc()}\n", encoding="utf-8")
        session.log_file.close()
    return 0 if finished else 1


if __name__ == "__main__":
    raise SystemExit(main())
