/* Catalogue init — GLightbox zoom viewer, Pagefind search modal, nav, scroll-top.
   Guarded so missing elements never throw (pages differ). */
(function () {
  "use strict";

  // GLightbox — the zoom/pan image viewer (reused from archivos_nuestros).
  if (window.GLightbox) {
    GLightbox({ selector: ".glightbox", zoomable: true, touchNavigation: true });
  }

  // Pagefind search: the standalone /search/ page and the header modal.
  if (window.SITE_HAS_SEARCH && window.PagefindUI) {
    if (document.getElementById("search")) {
      new PagefindUI({ element: "#search", showSubResults: true, showImages: false });
    }
    if (document.getElementById("search-modal-box")) {
      new PagefindUI({ element: "#search-modal-box", showSubResults: true, showImages: false });
    }
    const icon = document.getElementById("search-icon");
    const modalEl = document.getElementById("search-modal");
    if (icon && modalEl && window.bootstrap) {
      const modal = new bootstrap.Modal(modalEl);
      icon.addEventListener("click", () => modal.show());
    }
  }

  // Mobile nav toggle.
  const toggle = document.querySelector(".mobile-nav-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      document.body.classList.toggle("mobile-nav-active");
      toggle.classList.toggle("bi-list");
      toggle.classList.toggle("bi-x");
    });
  }

  // Scroll-to-top button.
  const scrollTop = document.querySelector(".scroll-top");
  if (scrollTop) {
    const toggleScrollTop = () =>
      window.scrollY > 100 ? scrollTop.classList.add("active") : scrollTop.classList.remove("active");
    scrollTop.addEventListener("click", (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    window.addEventListener("load", toggleScrollTop);
    document.addEventListener("scroll", toggleScrollTop);
  }
})();
