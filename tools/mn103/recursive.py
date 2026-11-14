"""
Recursive-descent MN103 disassembly: only decodes code reachable by
following control flow, so data is not mistaken for instructions.

Seeds: entry point(s), then iteratively
  - CALL / CALLS / JMP / Bcc targets inside reached code,
  - MOV imm32,An|Dn values that point into the code region (callbacks),
  - aligned u32 pointer tables (>= 3 consecutive pointers into code) found
    in non-code bytes (handler tables, vtables).

Result: dict addr -> (size, text, info), set of function starts.
"""
import struct
import mn103

END = {"RET", "RETF", "RETS", "RTI", "JMP", "BRA", "LRA"}
COND = {"BEQ", "BNE", "BGT", "BGE", "BLE", "BLT", "BHI", "BCC", "BLS", "BCS",
        "BVC", "BVS", "BNC", "BNS"}


class Disasm:
    def __init__(self, code, base):
        self.code, self.base = code, base
        self.end = base + len(code)
        self.ins = {}          # addr -> (size, text, info)
        self.owner = bytearray(len(code))   # 1 = byte belongs to decoded insn
        self.funcs = set()
        self.bad = set()       # seeds that hit undecodable bytes / overlaps

    def inside(self, a):
        return self.base <= a < self.end

    def _flow(self, start, work):
        stack = [start]
        while stack:
            a = stack.pop()
            while self.inside(a):
                if a in self.ins:
                    break
                off = a - self.base
                if self.owner[off]:          # lands in middle of an insn
                    self.bad.add(a)
                    break
                d = mn103.decode(self.code, off, a)
                if d is None:
                    self.bad.add(a)
                    break
                size, text, info = d
                if any(self.owner[off:off + size]):
                    self.bad.add(a)
                    break
                self.ins[a] = d
                self.owner[off:off + size] = b"\x01" * size
                mn = info["mn"]
                tgt = info.get("target")
                if mn in ("CALL", "CALLS"):
                    if tgt is not None and self.inside(tgt):
                        work.append(tgt)
                elif mn in COND or mn in ("JMP", "BRA"):
                    if tgt is not None and self.inside(tgt):
                        stack.append(tgt)
                if mn == "MOV" and "vals" in info:
                    for nm, (v, _sv, w) in info["vals"].items():
                        if w == 32 and nm.startswith("imm") and self.inside(v):
                            work.append(v)
                if mn in END:
                    break
                a += size

    def run(self, seeds, use_tables=True, rounds=4):
        work = list(seeds)
        for r in range(rounds):
            while work:
                f = work.pop()
                if f in self.ins or not self.inside(f):
                    continue
                n0 = len(self.ins)
                self._flow(f, work)
                if len(self.ins) > n0:
                    self.funcs.add(f)
            if not use_tables:
                break
            new = self.pointer_tables()
            new = [p for p in new if p not in self.ins]
            if not new:
                break
            work.extend(new)
        return self

    def pointer_tables(self, minrun=3):
        c, B = self.code, self.base
        out, run = [], []
        for off in range(0, len(c) - 3, 4):
            if self.owner[off]:
                if len(run) >= minrun:
                    out.extend(run)
                run = []
                continue
            v = struct.unpack_from("<I", c, off)[0]
            if self.inside(v):
                run.append(v)
            else:
                if len(run) >= minrun:
                    out.extend(run)
                run = []
        return out
