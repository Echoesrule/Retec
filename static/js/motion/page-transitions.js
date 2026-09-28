/* =============================================================================
   RETEC MOTION — page transitions
   -----------------------------------------------------------------------------
   A lightweight GSAP curtain between pages. Deliberately *not* Barba.js: this is
   a real multi-page Flask app, and a full DOM-swap library would add a second
   lifecycle on top of Jinja rendering, Flask redirects, CSRF-protected forms and
   the admin area — for a transition that only ever needs one panel.

   Handled here:
     · same-page hash links  → Lenis smooth scroll, header offset, no curtain
     · same-origin pages     → curtain wipes up, then a normal document load
     · everything else       → left entirely alone

   Never intercepted: external links, target=_blank, downloads, mailto/tel/sms,
   javascript:, modified clicks (⌘/ctrl/shift/middle), the admin area, any link
   marked data-no-transition, and form submissions.
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    var TRANSITION_KEY = 'retec:transition';
    var SKIP_SCHEME = /^(mailto:|tel:|sms:|javascript:|blob:|data:|about:|file:)/i;
    var BAIL_MS = 2200;

    function init() {
        if (!motion) return;

        var curtain = document.querySelector('.retec-curtain');
        var gsap = motion.live() ? motion.gsap : null;
        var running = false;

        /* ---------------------------------------------------------- scrolling */
        function scrollToHash(hash, pushHistory) {
            var node;
            try { node = document.querySelector(hash); } catch (error) { return false; }
            if (!node) return false;

            motion.scrollTo(node, {
                onComplete: function () {
                    /* Only move focus when the visitor actually asked to go
                       there, so keyboard users land inside the destination
                       without the scroll stealing focus mid-read. */
                    if (!node.hasAttribute('tabindex')) node.setAttribute('tabindex', '-1');
                    node.focus({ preventScroll: true });
                }
            });

            if (pushHistory && window.history && window.history.pushState) {
                window.history.pushState(null, '', hash);
            }
            return true;
        }

        /* A plain #hash on load (shared link, refresh) should still land
           correctly once the layout has settled. */
        function settleInitialHash() {
            if (!window.location.hash || window.location.hash === '#') return;
            window.setTimeout(function () {
                var node;
                try { node = document.querySelector(window.location.hash); } catch (error) { return; }
                if (!node) return;
                if (window.location.hash === '#hero') {
                    window.scrollTo(0, 0);
                    return;
                }
                motion.scrollTo(node);
            }, 60);
        }

        /* -------------------------------------------------------- transition */
        function go(href) {
            if (running) return;
            running = true;

            try { window.sessionStorage.setItem(TRANSITION_KEY, '1'); } catch (error) { /* private mode */ }

            if (!gsap || !curtain) {
                window.location.href = href;
                return;
            }

            motion.setScrollLocked(true);
            /* autoAlpha brings the curtain out of its `visibility: hidden`
               parked state; yPercent starts the wipe at the bottom edge. */
            motion.resetTransform(curtain);
            gsap.set(curtain, { yPercent: 101, autoAlpha: 1 });

            /* If the document never unloads, put the visitor back where they
               were rather than leaving them behind a curtain. */
            var bail = window.setTimeout(function () {
                running = false;
                motion.setScrollLocked(false);
                gsap.set(curtain, { yPercent: 101, autoAlpha: 0 });
            }, BAIL_MS);

            gsap.to(curtain, {
                yPercent: 0,
                duration: motion.duration.curtain,
                ease: motion.ease.curtain,
                onComplete: function () { window.location.href = href; }
            });

            motion.onCleanup(function () { window.clearTimeout(bail); });
        }

        /* -------------------------------------------------------------- click */
        function onClick(event) {
            if (event.defaultPrevented) return;
            if (event.button !== 0) return;
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

            var link = event.target.closest ? event.target.closest('a[href]') : null;
            if (!link) return;
            if (link.hasAttribute('download') || link.hasAttribute('data-no-transition')) return;
            if (link.target && link.target !== '_self') return;

            var href = link.getAttribute('href');
            if (!href || href === '#' || SKIP_SCHEME.test(href)) return;

            var url;
            try { url = new URL(link.href, window.location.href); } catch (error) { return; }
            if (url.origin !== window.location.origin) return;
            if (url.protocol !== 'http:' && url.protocol !== 'https:') return;

            /* The admin area keeps its plain, instant navigation. */
            if (url.pathname === '/admin' || url.pathname.indexOf('/admin/') === 0) return;

            var samePage = url.pathname === window.location.pathname
                && url.search === window.location.search;

            if (url.hash && url.hash !== '#') {
                if (samePage) {
                    event.preventDefault();
                    scrollToHash(url.hash, true);
                }
                /* Cross-page hashes go through the curtain like any page. */
                return;
            }

            if (samePage) return;

            event.preventDefault();
            go(url.href);
        }

        /* A back/forward that lands on a hash must settle, not jump. */
        function onPopState() {
            if (window.location.hash && window.location.hash !== '#') {
                window.setTimeout(function () { scrollToHash(window.location.hash, false); }, 20);
            }
        }

        document.addEventListener('click', onClick);
        window.addEventListener('popstate', onPopState);

        motion.onCleanup(function () {
            document.removeEventListener('click', onClick);
            window.removeEventListener('popstate', onPopState);
        });

        motion.onReady(settleInitialHash);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})(window, document);
