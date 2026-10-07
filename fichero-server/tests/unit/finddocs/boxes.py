"""Synthetic boxes with a known answer, for Find the Documents (spec: docs/contributor_manual/specs/source/finding-documents.md).

No real archive text: the Istmina box's STRUCTURE ("What the first real box taught", 2026-10-07) rebuilt
with invented names and words. Eight judgments of one labour court, in date order; each opens with the
court's caption, a place-and-date line and VISTOS, copies its case record into its body (a complaint
begins mid-page, as the real copies do), and closes with FALLA, "Cópiese, notifíquese" and typed
"(fdo)" signatures. Every written page is followed by its blank verso; two leaves were photographed
twice. Four of the eight cases are against the same company, so a company alone must not make a group.

The second box mixes letters, cables and a receipt, in Spanish and English, with two correspondences
whose letters answer each other.

Each box is a list of `Page`s (its text, whether it is blank, which shot it repeats) and the person's
breakdown: each document's page ids in order.
"""
from __future__ import annotations

from dataclasses import dataclass, field

COMPANY = "Compañía Minera del Alto San Juan"
JUDGE = "Aurelio Quintero Lemos"

#: (date line, plaintiff, defendant, subject, body pages, folio numbers on body pages, duplicate body page)
_CASES = [
    ("12 de enero de 1948", "Pedro Mosquera Rentería", COMPANY, "salarios", 2, False, None),
    ("3 de febrero de 1948", "Lucía Valencia Murillo", "Tomás Ibargüen Cuesta", "prestaciones", 3, False, None),
    ("27 de febrero de 1948", "Jacinto Asprilla Moreno", COMPANY, "cesantía", 2, False, 1),
    ("15 de marzo de 1948", "Rosa Emilia Copete", "Hacienda La Esperanza", "salarios", 1, False, None),
    ("9 de abril de 1948", "Nicanor Perea Lozano", COMPANY, "accidente de trabajo", 3, True, None),
    ("30 de abril de 1948", "Eusebio Chaverra Mena", "Compañía de Transportes del Atrato", "vacaciones", 2, True, 2),
    ("21 de mayo de 1948", "Dominga Palacios Rivas", COMPANY, "despido", 2, True, None),
    ("18 de junio de 1948", "Marcelino Rengifo Hinestroza", "Aserrío El Progreso", "salarios", 1, False, None),
]


@dataclass
class Page:
    id: str
    text: str
    blank: bool = False
    #: The id of the page this one is a second shot of.
    repeats: str | None = None
    ink: float = field(init=False)

    def __post_init__(self) -> None:
        self.ink = 0.002 if self.blank else 0.06


def _caption(date: str, plaintiff: str, defendant: str, subject: str) -> str:
    return (
        "JUZGADO DEL TRABAJO DEL CIRCUITO\n"
        f"Istmina, {date}.\n"
        "VISTOS:\n"
        f"Por demanda presentada ante este Juzgado, el señor {plaintiff}, demandante, mayor de edad y vecino "
        f"de este municipio, promovió juicio ordinario de trabajo contra {defendant}, para que se le condene "
        f"al pago de {subject} y de las costas del juicio. Admitida la demanda se corrió traslado a la parte "
        "demandada, que la contestó dentro del término legal oponiéndose a las pretensiones del actor y\n"
        "proponiendo las excepciones que consideró del caso.\n"
        + ".\n".join(_sentences(hash_of(plaintiff), 2))
        + ", todo lo cual se estudia con el detenimiento que el asunto requiere, pues de ello depende la suerte"
    )


def hash_of(text: str) -> int:
    return sum(ord(c) * (i + 1) for i, c in enumerate(text))


#: Sentences a judgment's body is made of; each page draws its own, so no two pages read alike.
_SENTENCES = [
    "Se oyeron los testimonios de los compañeros de trabajo del demandante, quienes declararon sobre el tiempo de servicio",
    "El Juzgado practicó una inspección ocular en las dependencias de la empresa, cuyo resultado consta en el acta",
    "La parte demandada allegó copia del contrato de trabajo y de las planillas de pago de los últimos meses",
    "Del examen de las pruebas se concluye que la relación de trabajo existió durante el tiempo alegado",
    "El apoderado del actor presentó su alegato de conclusión dentro del término señalado por la ley",
    "No aparece demostrado que el trabajador hubiera recibido el pago de las prestaciones que reclama",
    "El perito designado rindió su dictamen sobre el valor de los salarios dejados de pagar",
    "La excepción de prescripción no puede prosperar porque la demanda se presentó a tiempo",
    "Obra en autos la certificación del alcalde sobre el jornal que se pagaba en la región",
    "El representante de la empresa absolvió el interrogatorio de parte en la audiencia respectiva",
    "Las declaraciones recibidas son concordantes y merecen plena credibilidad al Juzgado",
    "La jurisprudencia del Tribunal Supremo del Trabajo ha sostenido reiteradamente la misma doctrina",
    "Se allegaron al expediente las cartas cruzadas entre las partes durante el tiempo del contrato",
    "El demandado alegó que el actor abandonó el trabajo sin justa causa, hecho que no demostró",
    "Consta que el trabajador sufrió una lesión en el desempeño de sus labores en la mina",
    "El médico legista dictaminó una incapacidad que se tendrá en cuenta para la indemnización",
    "Las partes no llegaron a un acuerdo en la audiencia de conciliación celebrada en el despacho",
    "El salario básico se fija con base en la prueba testimonial y en las planillas aportadas",
    "La empresa no acreditó haber consignado las sumas debidas a órdenes del Juzgado",
    "En consecuencia se impone acceder a las súplicas de la demanda en la forma que se dirá",
]
_AMOUNTS = ["trescientos veinte", "ciento ochenta", "cuatrocientos diez", "doscientos cincuenta", "seiscientos",
            "noventa y cinco", "quinientos treinta", "ciento cuarenta"]


def _sentences(seed: int, k: int) -> list[str]:
    import random

    return random.Random(seed).sample(_SENTENCES, k)


def _body(case: int, n: int, plaintiff: str, folio: int | None, runs_over: bool, last_open: bool) -> str:
    head = f"- {folio} -\n" if folio else ""
    opening = "de la acción intentada. " if runs_over else ""
    insert = ""
    if n == 0:
        # A copy of the complaint begins mid-page, as the copies inside the real judgments do.
        insert = (f"El libelo dice así en lo pertinente: Señor Juez del Trabajo: {plaintiff}, mayor de edad, "
                  "respetuosamente manifiesto a usted que presto mis servicios desde hace varios años. ")
    lines = _sentences(case * 10 + n, 4)
    body = ".\n".join(lines)
    return head + opening + insert + body + (" y que" if last_open else ".")


def _closing(case: int, plaintiff: str, defendant: str, subject: str, folio: int | None) -> str:
    head = f"- {folio} -\n" if folio else ""
    reason = _sentences(case * 10 + 9, 1)[0]
    return (head + f"{reason}, por lo cual el Juzgado del Trabajo, administrando justicia en nombre de la "
            "República y por autoridad de la ley,\nFALLA:\n"
            f"Primero. Condénase a {defendant} a pagar a {plaintiff} la suma de {_AMOUNTS[case - 1]} pesos por "
            f"concepto de {subject}.\nSegundo. Sin costas.\nCópiese, notifíquese y cúmplase.\n"
            f"El Juez,\n(fdo) {JUDGE}\nEl Secretario,\n(fdo) Abigaíl Cuesta")


def istmina_box() -> tuple[list[Page], list[list[str]]]:
    """The 1948 register: eight judgments, blank versos, two duplicate shots. Returns (pages, truth)."""
    pages: list[Page] = []
    truth: list[list[str]] = []
    for c, (date, plaintiff, defendant, subject, body_pages, folios, duplicate) in enumerate(_CASES, start=1):
        written = [_caption(date, plaintiff, defendant, subject)]
        for b in range(body_pages):
            # The first body page runs on from the caption page mid-sentence; later ones start afresh, and
            # some end mid-sentence (the next starts afresh all the same: the join is the cues' to judge).
            written.append(_body(c, b, plaintiff, b + 2 if folios else None, runs_over=(b == 0),
                                 last_open=(b % 2 == 1)))
        written.append(_closing(c, plaintiff, defendant, subject, body_pages + 2 if folios else None))
        document: list[str] = []
        for w, text in enumerate(written, start=1):
            recto = Page(f"s{c}-p{w}", text)
            verso = Page(f"s{c}-p{w}v", "", blank=True)
            pages += [recto, verso]
            document += [recto.id, verso.id]
            if duplicate is not None and w == duplicate + 1:
                # The same leaf shot again: a reading of the second shot differs in a few characters.
                again = Page(f"s{c}-p{w}-again", text.replace("el ", "cl ", 2),
                             repeats=recto.id)
                again_verso = Page(f"s{c}-p{w}-again-v", "", blank=True)
                pages += [again, again_verso]
                document += [again.id, again_verso.id]
        truth.append(document)
    return pages, truth


def correspondence_box() -> tuple[list[Page], list[list[str]], list[list[int]]]:
    """Letters, cables and a receipt, Spanish and English. Returns (pages, truth, the groups by document index)."""
    documents = [
        # 0: a letter of two pages, signed.
        ["Andagoya, 3 de abril de 1947.\nSeñor Don Ricardo Palacios,\nQuibdó.\nMuy señor mío:\n"
         "Tengo el gusto de comunicarle que la madera que usted encargó saldrá en la lancha del próximo martes,\n"
         "junto con los víveres que pidió para la tienda de su hermano, y que el valor de los fletes",
         "quedará a cargo de la compañía según lo convenido en nuestra última conversación.\n"
         "Le ruego avisarme si la carga llega completa.\nAtentamente,\nJorge Mosquera"],
        # 1: a cable, no closing.
        ["TELEGRAMA\nQuibdó, 5 de abril de 1947\nJORGE MOSQUERA ANDAGOYA\n"
         "RECIBIDA SU CARTA STOP ESPERO LANCHA MARTES STOP ENVIE FACTURA STOP PALACIOS"],
        # 2: the reply to 0.
        ["Quibdó, 9 de abril de 1947.\nSeñor Don Jorge Mosquera,\nAndagoya.\n"
         "Recibí su atenta carta del tres de los corrientes y le agradezco las noticias sobre la madera.\n"
         "La carga llegó completa y en buen estado.\nSu seguro servidor,\nRicardo Palacios"],
        # 3: an English letter of two pages.
        ["London, 3 March 1948\nDear Mr. Brown,\n"
         "We have received your report on the dredging season at the Condoto works and the board has asked\n"
         "me to say that the figures for gold recovered are most encouraging, though the costs of fuel",
         "remain higher than we had hoped when the estimates were drawn up last autumn.\n"
         "Please send the revised accounts by the next mail.\nYours faithfully,\nJohn Smith"],
        # 4: an English cable.
        ["CABLEGRAM\nNew York, March 10, 1948\nBROWN ANDAGOYA ARRIVING CARTAGENA TWENTIETH STOP MEET LAUNCH"],
        # 5: the reply to 3, two pages.
        ["Andagoya, 20 March 1948\nDear Mr. Smith,\n"
         "Thank you for your letter of the third. The revised accounts go with this mail, and you will see\n"
         "that the fuel costs have come down since the new launch began carrying oil from Cartagena, which",
         "should please the board when it meets next month.\nYours sincerely,\nRobert Brown"],
        # 6: a receipt.
        ["RECIBO\nRecibí del señor Jorge Mosquera la suma de cien pesos por fletes de madera.\n"
         "Andagoya, 2 de mayo de 1947.\nJuan Bautista Lemos"],
    ]
    pages: list[Page] = []
    truth: list[list[str]] = []
    for d, texts in enumerate(documents, start=1):
        ids: list[str] = []
        for p, text in enumerate(texts, start=1):
            page = Page(f"d{d}-p{p}", text)
            pages.append(page)
            ids.append(page.id)
            if d in (1, 4):  # the two long letters were photographed with their blank backs
                verso = Page(f"d{d}-p{p}v", "", blank=True)
                pages.append(verso)
                ids.append(verso.id)
            if d == 6 and p == 1:  # the reply's first leaf shot twice
                again = Page(f"d{d}-p{p}-again", text.replace("Thank", "Thanh"), repeats=page.id)
                pages.append(again)
                ids.append(again.id)
        truth.append(ids)
    return pages, truth, [[0, 2], [3, 5]]
