import json
from datetime import datetime
from pathlib import Path


LOG_DIR = Path("logs")


class ScraperAudit:
    def __init__(self, portal, search_url=None):
        self.portal = portal
        self.search_url = search_url
        self.total_reported = None
        self.pages_expected = None
        self.pages_planned = None
        self.page_size = None
        self.limit_reason = None
        self.page_results = []
        self.processing_counts = {}
        self.omissions = {}
        self.errors = []
        self.notes = []

    def set_listing_summary(
        self,
        total_reported=None,
        pages_expected=None,
        pages_planned=None,
        page_size=None,
        limit_reason=None,
    ):
        self.total_reported = total_reported
        self.pages_expected = pages_expected
        self.pages_planned = pages_planned
        self.page_size = page_size
        self.limit_reason = limit_reason

    def record_page(
        self,
        page_number,
        url=None,
        links_count=0,
        new_links_count=0,
        duplicate_links_count=0,
        status="ok",
        reason=None,
    ):
        self.page_results.append(
            {
                "page": page_number,
                "url": url,
                "links": links_count,
                "new_links": new_links_count,
                "duplicate_links": duplicate_links_count,
                "status": status,
                "reason": reason,
            }
        )

    def record_scroll(self, scroll_number, links_count=0, new_links_count=0, duplicate_links_count=0):
        self.record_page(
            page_number=f"scroll_{scroll_number}",
            links_count=links_count,
            new_links_count=new_links_count,
            duplicate_links_count=duplicate_links_count,
            status="ok",
        )

    def record_omission(self, reason, link=None):
        self.omissions[reason] = self.omissions.get(reason, 0) + 1
        if link:
            self.notes.append({"type": "omission", "reason": reason, "link": link})

    def record_error(self, link, error):
        self.errors.append({"link": link, "error": str(error)})

    def set_processing_counts(self, **counts):
        self.processing_counts = counts

    def add_note(self, message):
        self.notes.append({"type": "note", "message": message})

    def duplicate_links_total(self):
        return sum(int(item.get("duplicate_links") or 0) for item in self.page_results)

    def failed_pages(self):
        return [item for item in self.page_results if item.get("status") != "ok"]

    def empty_pages(self):
        return [
            item
            for item in self.page_results
            if item.get("status") == "ok" and int(item.get("links") or 0) == 0
        ]

    def missing_reasons(self, found_links_count):
        if not self.total_reported or self.total_reported <= found_links_count:
            return []

        reasons = []

        if self.limit_reason:
            reasons.append(self.limit_reason)

        failed = self.failed_pages()
        if failed:
            details = ", ".join(
                f"{item.get('page')} ({item.get('reason') or 'sin detalle'})"
                for item in failed[:5]
            )
            reasons.append(f"{len(failed)} pagina(s) no se pudieron revisar correctamente: {details}.")

        empty = self.empty_pages()
        if empty:
            pages = ", ".join(str(item.get("page")) for item in empty[:8])
            reasons.append(f"{len(empty)} pagina(s) no devolvieron links visibles: {pages}.")

        duplicates = self.duplicate_links_total()
        if duplicates:
            reasons.append(
                f"{duplicates} link(s) repetidos entre paginas/scrolls no se contaron dos veces."
            )

        if self.omissions:
            readable = ", ".join(
                f"{reason}: {count}" for reason, count in sorted(self.omissions.items())
            )
            reasons.append(f"Omisiones durante el procesamiento: {readable}.")

        reasons.append(
            "Si aun quedan faltantes, el portal reporto mas resultados que los enlaces visibles "
            "con los selectores actuales; puede ser carga diferida, anuncios patrocinados sin URL "
            "compatible, duplicados ocultos o un cambio de HTML del sitio."
        )

        return reasons

    def print_summary(self, found_links_count):
        print("\n[AUDITORIA] Cobertura del scraper")
        print(f"[AUDITORIA] Portal: {self.portal}")
        if self.search_url:
            print(f"[AUDITORIA] URL busqueda: {self.search_url}")
        print(f"[AUDITORIA] Total reportado por portal: {self.total_reported}")
        print(f"[AUDITORIA] Paginas esperadas: {self.pages_expected}")
        print(f"[AUDITORIA] Paginas/scrolls revisados: {len(self.page_results)}")
        print(f"[AUDITORIA] Links unicos encontrados: {found_links_count}")

        for item in self.page_results:
            detail = (
                f"[AUDITORIA] {item['page']}: {item['links']} links "
                f"({item['new_links']} nuevos, {item['duplicate_links']} repetidos)"
            )
            if item.get("status") != "ok":
                detail += f" - {item.get('status')}: {item.get('reason')}"
            print(detail)

        if self.total_reported and found_links_count < self.total_reported:
            missing = self.total_reported - found_links_count
            print(f"[WARN] Faltan {missing} anuncios frente al total reportado.")
            print("[WARN] Motivos por los que no se incluyeron todos:")
            for reason in self.missing_reasons(found_links_count):
                print(f"[WARN] - {reason}")

    def to_dict(self, found_links_count):
        return {
            "portal": self.portal,
            "search_url": self.search_url,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "total_reported": self.total_reported,
            "pages_expected": self.pages_expected,
            "pages_planned": self.pages_planned,
            "page_size": self.page_size,
            "found_links_count": found_links_count,
            "page_results": self.page_results,
            "processing_counts": self.processing_counts,
            "omissions": self.omissions,
            "errors": self.errors,
            "notes": self.notes,
            "missing_reasons": self.missing_reasons(found_links_count),
        }

    def save(self, found_links_count):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        portal_slug = self.portal.lower().replace(" ", "_")
        path = LOG_DIR / f"auditoria_{portal_slug}_{timestamp}.json"
        with path.open("w", encoding="utf-8") as file:
            json.dump(self.to_dict(found_links_count), file, ensure_ascii=False, indent=2)
        print(f"[AUDITORIA] Archivo guardado: {path}")
        return path
