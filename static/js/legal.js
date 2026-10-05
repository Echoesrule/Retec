/* =============================================================================
   RETEC MOTION — legal page navigation
   -----------------------------------------------------------------------------
   Scroll-aware table of contents for /privacy, /terms and /security.

   Scrolling is not implemented here. The TOC emits ordinary `href="#slug"`
   anchors, and page-transitions.js already intercepts same-page hashes, calls
   motion.scrollTo() with the correct header offset, pushes the hash and moves
   focus for keyboard users. Adding a second scroll implementation would be two
   systems fighting over one scroll position.

   So this module only answers one question: which section is the reader in?

   Design notes:
     · IntersectionObserver, not a scroll listener. The active section is derived
       from a band just below the sticky header, not from scroll position, so a
       fast flick through a long page produces the same answer as a slow read.
     · No layout writes. Only class and aria-current change, so nothing reflows
       and there is no scroll-jump feedback loop.
     · Reduced motion does not disable this — knowing where you are on the page
       is information, not decoration. It only disables the mobile rail's
       horizontal auto-scroll easing, which is pure motion for its own sake.

   One thing this module measures rather than animates: the sticky site header.
   Both sticky navs here (the mobile rail, the desktop aside) have to sit below
   it, and its height is not expressible in CSS — it changes with the viewport
   and with the nav's own content. It is published as --legal-header-h so the
   stylesheet can position against it. Without that, the rail sticks at top:0
   behind a z-index:100 header and is invisible for the entire read.
   ========================================================================== */
(function (window, document) {
    'use strict';

    var motion = window.RETEC_MOTION;

    /* Matches --motion-header-offset plus the sticky header's own height. The
       observer band starts here so a section becomes current as its heading
       clears the header, which is where the reader's eye already is. */
    var BAND_TOP = 140;

    function init() {
        publishHeaderHeight();
        var sections = [].slice.call(document.querySelectorAll('[data-legal-section]'));
        if (!sections.length) return;

        var links = [].slice.call(document.querySelectorAll('[data-legal-toc]'));
        var rail = document.querySelector('.legal__rail-list');
        var currentId = null;

    function reduced() {
        return !!(motion && motion.reduced && motion.reduced());
    }

    /* Publishes the sticky header's height for the stylesheet's sticky offsets.
       A ResizeObserver rather than a resize listener, because the header also
       changes height when the nav reflows — not only when the window resizes.

       Guarded: a cross-browser gap in ResizeObserver must not take the scroll
       spy down with it, so the fallback is a one-shot read on load. */
    function publishHeaderHeight() {
        var header = document.getElementById('header');
        if (!header) return;

        function publish() {
            var height = header.offsetHeight;
            if (!height) return;
            document.documentElement.style.setProperty('--legal-header-h', height + 'px');
        }

        publish();

        if (!window.ResizeObserver) return;
        var observer = new window.ResizeObserver(publish);
        observer.observe(header);
        if (motion && motion.onCleanup) {
            motion.onCleanup(function () { observer.disconnect(); });
        }
    }

        function setActive(id, force) {
            /* Early-out on an unchanged id. Without it every observer callback
               would restart the rail's smooth scroll, which fights the reader's
               own horizontal dragging. */
            if (!force && id === currentId) return;
            currentId = id;

            links.forEach(function (link) {
                if (link.getAttribute('data-legal-toc') === id) {
                    link.classList.add('is-active');
                    link.setAttribute('aria-current', 'true');
                } else {
                    link.classList.remove('is-active');
                    link.removeAttribute('aria-current');
                }
            });

            /* Keep the current chip in view in the mobile rail without touching
               the page scroll: scrollLeft is set directly, so no ancestor is
               scrolled by accident. The rail's own link is looked up inside the
               rail — both navs emit the same data-legal-toc value. */
            if (!rail || rail.scrollWidth <= rail.clientWidth) return;
            var link = rail.querySelector('[data-legal-toc="' + id + '"]');
            if (!link || !link.offsetParent) return;

            var target = link.offsetLeft - (rail.clientWidth - link.offsetWidth) / 2;
            var max = rail.scrollWidth - rail.clientWidth;
            rail.scrollTo({
                left: Math.max(0, Math.min(target, max)),
                behavior: reduced() ? 'auto' : 'smooth'
            });
        }

        if (!window.IntersectionObserver) return;

        /* Sections currently inside the band. A set rather than a counter so a
           fast scroll that skips a section cannot leave it stuck as active. */
        var visible = new Set();

        function resolve() {
            /* Topmost visible section wins, so the reader is credited with the
               section they are reading rather than the last one that started. */
            for (var i = 0; i < sections.length; i += 1) {
                if (visible.has(sections[i])) {
                    setActive(sections[i].getAttribute('data-legal-section'));
                    return;
                }
            }

            /* Nothing in the band. Either the page is above the first section
               (the hero) or the reader is past a short trailing section, so fall
               back to the last section that has already gone past the band. This
               read is a layout query, not a write, and it only runs on an
               observer callback. */
            var band = window.innerHeight * 0.35;
            var fallback = sections[0];
            for (var j = 0; j < sections.length; j += 1) {
                if (sections[j].getBoundingClientRect().top < band) fallback = sections[j];
            }
            setActive(fallback.getAttribute('data-legal-section'));
        }

        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) visible.add(entry.target);
                else visible.delete(entry.target);
            });
            resolve();
        }, {
            /* A band from just under the header to a third of the way down.
               rootMargin percentages are relative to the root, so the bottom
               edge keeps the observer honest about tall sections. */
            rootMargin: '-' + BAND_TOP + 'px 0px -60% 0px',
            threshold: 0
        });

        sections.forEach(function (section) { observer.observe(section); });

        /* Mark the first section immediately: the server-rendered default is
           correct for a reader at the top, and this keeps it correct if the
           browser restores a scroll position on a reload. */
        setActive(sections[0].getAttribute('data-legal-section'), true);

        if (motion && motion.onCleanup) {
            motion.onCleanup(function () {
                observer.disconnect();
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})(window, document);
