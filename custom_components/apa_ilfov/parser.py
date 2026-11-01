"""Parser pentru facturile Apa-Canal Ilfov (PDF atașat + text e-mail).

Modul pur Python (fără dependențe de Home Assistant), ca să poată fi testat separat.
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

# Număr în format românesc: 1.234,56 sau 234,56 (separator de mii opțional)
NUM = r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}"
_NUM_RE = re.compile(NUM)

MONTHS = {
    "IANUARIE": 1, "FEBRUARIE": 2, "MARTIE": 3, "APRILIE": 4, "MAI": 5,
    "IUNIE": 6, "IULIE": 7, "AUGUST": 8, "SEPTEMBRIE": 9,
    "OCTOMBRIE": 10, "NOIEMBRIE": 11, "DECEMBRIE": 12,
}

_ROW_RE = re.compile(
    rf"({NUM})(\d)\s*MC\s+({NUM})\s+({NUM})\s*(.*?)(APA|CANAL)(?![A-Za-z])"
)
_DATE = r"(\d{2}\.\d{2}\.\d{4})"

TOL = 0.011


def ro_num(text: str) -> float:
    """'1.234,56' -> 1234.56"""
    return float(text.replace(".", "").replace(",", "."))


def _ro_date(text: str) -> date:
    return datetime.strptime(text, "%d.%m.%Y").date()


def _strip_diacritics(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


@dataclass
class Linie:
    """O linie de serviciu din factură (apă sau canal)."""

    cantitate: float = 0.0  # m3
    pret: float = 0.0  # lei / m3
    valoare: float = 0.0  # lei fără TVA
    tva: float = 0.0  # lei
    index_vechi: float | None = None
    index_nou: float | None = None
    tip: str | None = None  # Estimat / Citit / Autocitit ...


@dataclass
class Factura:
    serie: str = ""
    numar: str = ""
    emisa: str | None = None  # ISO
    scadenta: str | None = None  # ISO
    luna: int = 0
    an: int = 0
    total: float = 0.0
    persoane: int | None = None
    apa: Linie | None = None
    canal: Linie | None = None
    sursa: str = "pdf"  # pdf | mail
    ajustare: float = 0.0  # total − suma liniilor (negativ = credit / sold anterior)
    avertismente: list[str] = field(default_factory=list)

    @property
    def cheie(self) -> str:
        if self.serie and self.numar:
            return f"{self.serie}-{self.numar}"
        return f"mail-{self.emisa}-{self.total:.2f}"

    @property
    def perioada(self) -> str:
        return f"{self.an:04d}-{self.luna:02d}"

    @property
    def verificata(self) -> bool:
        return not self.avertismente

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Factura":
        data = dict(data)
        for k in ("apa", "canal"):
            if data.get(k):
                data[k] = Linie(**data[k])
        return cls(**data)


class ParseError(Exception):
    """PDF-ul nu seamănă cu o factură Apa-Canal Ilfov."""


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader  # import târziu: dependență opțională la test

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def _linie(m: re.Match) -> Linie:
    tva, _nr, qty, pret, rest, _label = m.groups()
    nums = [ro_num(x) for x in _NUM_RE.findall(rest)]
    tip_m = re.search(r"([^\W\d_]+)\s*$", rest)
    ln = Linie(
        cantitate=ro_num(qty),
        pret=ro_num(pret),
        tva=ro_num(tva),
        tip=tip_m.group(1) if tip_m else None,
    )
    if len(nums) >= 3:
        ln.valoare, ln.index_nou, ln.index_vechi = nums[-3], nums[-2], nums[-1]
    elif nums:
        ln.valoare = nums[0]
    return ln


def parse_pdf_text(text: str) -> Factura:
    flat = re.sub(r"[ \t]+", " ", text)
    f = Factura(sursa="pdf")

    m = re.search(r"Seria\s+([A-Z0-9]+)\s+(\d+)", flat)
    if not m or "FACTURA" not in flat:
        raise ParseError("nu pare o factură Apa-Canal Ilfov")
    f.serie, f.numar = m.group(1), m.group(2)

    for pat, attr in (
        (rf"{_DATE}\s*Data emiterii|Data emiterii\s+{_DATE}", "emisa"),
        (rf"Data scadentei\s+{_DATE}", "scadenta"),
    ):
        dm = re.search(pat, flat)
        if dm:
            val = next(g for g in dm.groups() if g)
            setattr(f, attr, _ro_date(val).isoformat())

    pm = re.search(r"Perioada facturare\s+([A-Za-zĂÂÎȘȚŞŢăâîșțşţ]+)\s*/\s*(\d{4})", flat)
    if pm:
        luna = MONTHS.get(_strip_diacritics(pm.group(1)).upper())
        if luna:
            f.luna, f.an = luna, int(pm.group(2))
    if not f.luna and f.emisa:
        # fallback: luna dinaintea emiterii
        d = date.fromisoformat(f.emisa)
        f.luna, f.an = (d.month - 1 or 12), (d.year if d.month > 1 else d.year - 1)
        f.avertismente.append("perioada dedusă din data emiterii")

    tm = re.search(rf"TOTAL DE PLATA\s+({NUM})", flat)
    if tm:
        f.total = ro_num(tm.group(1))
    else:
        f.avertismente.append("totalul de plată nu a fost găsit")

    pers = re.search(r"Nr\. Persoane:\s*(\d+)", flat)
    if pers:
        f.persoane = int(pers.group(1))

    for m in _ROW_RE.finditer(flat):
        ln = _linie(m)
        if m.group(6) == "APA" and f.apa is None:
            f.apa = ln
        elif m.group(6) == "CANAL" and f.canal is None:
            f.canal = ln

    if f.apa is None:
        raise ParseError("linia de apă nu a fost găsită")

    _verifica(f)
    return f


def _verifica(f: Factura) -> None:
    w = f.avertismente
    for nume, ln in (("apă", f.apa), ("canal", f.canal)):
        if ln is None:
            continue
        if abs(ln.pret * ln.cantitate - ln.valoare) > 0.02 * max(1.0, ln.cantitate):
            w.append(f"{nume}: preț × cantitate ≠ valoare")
        if ln.index_nou is not None and ln.index_vechi is not None:
            if abs((ln.index_nou - ln.index_vechi) - ln.cantitate) > TOL:
                w.append(f"{nume}: index nou − vechi ≠ cantitate")
    suma = sum((ln.valoare + ln.tva) for ln in (f.apa, f.canal) if ln)
    if f.total and abs(suma - f.total) > 0.02:
        f.ajustare = round(f.total - suma, 2)
        if f.ajustare > 0:
            # total mai mare decât liniile: ceva în plus (penalități etc.) -> de verificat
            w.append("suma liniilor ≠ total de plată")
        # total mai mic: credit / sold anterior (ex. regularizare după schimbarea
        # apometrului) -> doar informativ, vezi `ajustare`


def parse_pdf(data: bytes) -> Factura:
    return parse_pdf_text(pdf_text(data))


def parse_body(text: str, trimis: datetime | None = None) -> Factura | None:
    """Factură „provizorie” doar din textul e-mailului (când lipsește PDF-ul)."""
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = t.replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"valoare de (\d+(?:[.,]\d{1,2})?)(?:\s*lei)?", t, re.I)
    if not m:
        return None
    f = Factura(sursa="mail", total=float(m.group(1).replace(",", ".")))
    sm = re.search(r"scadent[aă]\s*:?\s*" + _DATE, t, re.I)
    if sm:
        f.scadenta = _ro_date(sm.group(1)).isoformat()
    em = re.search(r"emis[aă]\s+(?:la|pe)?\s*" + _DATE, t, re.I)
    if em:
        f.emisa = _ro_date(em.group(1)).isoformat()
    elif trimis:
        f.emisa = trimis.date().isoformat()
    if not f.scadenta and f.emisa:
        from datetime import timedelta

        f.scadenta = (date.fromisoformat(f.emisa) + timedelta(days=15)).isoformat()
    f.avertismente.append("doar din text e-mail (fără PDF)")
    return f
