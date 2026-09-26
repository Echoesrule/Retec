/* =============================================================================
   RETEC MOTION — navigation
   -----------------------------------------------------------------------------
   Interaction only. The navbar keeps its existing editorial shape: no pill, no
   restyle, no new chrome beyond a 2px scroll-progress hairline aligned to the
   RETEC grid.

     · scroll progress   scrubbed against the document
     · header state      the design's own .header--scrolled class
     · link movement     a 2px rise, spring-eased, fine pointers only
     · mobile menu       staggered item reveal while the design stays intact
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    function init() {
        if (!motion) return;

        var header = document.getElementById('header');
        var navMenu = document.getElementById('nav-menu');
        var navLinks = Array.prototype.slice.call(document.querySelectorAll('.nav__link, .nav__chat'));

        /* ------------------------------------------------- scroll progress */
        var bar = null;
        /* An article page ships its own, more precise reading-progress bar.
           Two hairlines at the same edge would just fight each other. */
        var hasOwnProgress = !!document.querySelector('.reading-progress');

        if (motion.live() && motion.ScrollTrigger && !hasOwnProgress) {
            bar = document.createElement('div');
            bar.className = 'retec-scroll-progress';
            bar.setAttribute('aria-hidden', 'true');
            document.body.appendChild(bar);

            motion.gsap.to(bar, {
                scaleX: 1,
                ease: 'none',
                scrollTrigger: {
                    id: 'retec-scroll-progress',
                    trigger: document.documentElement,
                    start: 'top top',
                    end: 'bottom bottom',
                    scrub: 0.2
                }
            });

            motion.onCleanup(function () { if (bar && bar.parentNode) bar.parentNode.removeChild(bar); });
        }

        /* ---------------------------------------------------- header state */
        if (header) {
            var ticking = false;
            var onScroll = function () {
                if (ticking) return;
                ticking = true;
                window.requestAnimationFrame(function () {
                    header.classList.toggle('header--scrolled', window.pageYOffset > 60);
                    ticking = false;
                });
            };
            onScroll();
            window.addEventListener('scroll', onScroll, { passive: true });
            motion.onCleanup(function () { window.removeEventListener('scroll', onScroll); });
        }

        /* ----------------------------------------------------- link motion */
        if (motion.live() && motion.gsap && motion.fine()) {
            var gsap = motion.gsap;

            navLinks.forEach(function (link) {
                /* Links inside a link are not interactive on their own. */
                if (link.querySelector('a')) return;

                /* GSAP is the only writer of transform on a nav item, so the
                   CSS custom-property hover shift is removed rather than
                   doubled with the tween below. */
                motion.resetTransform(link);
                var setY = gsap.quickTo(link, 'y', { duration: 0.4, ease: 'power3.out' });

                var onEnter = function () { setY(-2); };
                var onLeave = function () { setY(0); };

                link.addEventListener('pointerenter', onEnter);
                link.addEventListener('pointerleave', onLeave);
                link.addEventListener('focus', onEnter);
                link.addEventListener('blur', onLeave);

                motion.onCleanup(function () {
                    link.removeEventListener('pointerenter', onEnter);
                    link.removeEventListener('pointerleave', onLeave);
                    link.removeEventListener('focus', onEnter);
                    link.removeEventListener('blur', onLeave);
                    gsap.killTweensOf(link);
                });
            });
        }

        /* --------------------------------------------------- mobile menu */
        if (navMenu) {
            var items = Array.prototype.slice.call(navMenu.querySelectorAll('.nav__list > li'));
            /* Matches the design's own drawer breakpoint exactly. */
            var drawerQuery = window.matchMedia('(max-width: 768px)');
            var isDrawer = drawerQuery.matches;

            /* Only prime the hidden state where the menu is actually a drawer. */
            if (isDrawer && motion.live() && motion.gsap) {
                var gsapMenu = motion.gsap;
                gsapMenu.set(items, { y: 14, opacity: 0 });
            }

            var releaseItems = function () {
                if (!motion.gsap) return;
                motion.gsap.killTweensOf(items);
                motion.gsap.set(items, { clearProps: 'transform,opacity' });
            };
            motion.onCleanup(releaseItems);

            /* script.js owns the open/close state; this only animates it. */
            var lastOpen = null;
            function sync() {
                var open = navMenu.classList.contains('nav__menu--open');
                if (open === lastOpen) return;
                lastOpen = open;

                if (!isDrawer || !motion.live() || !motion.gsap) return;

                if (open) {
                    motion.gsap.to(items, {
                        y: 0,
                        opacity: 1,
                        duration: motion.duration.medium,
                        stagger: motion.stagger.sm,
                        ease: motion.ease.expressive,
                        overwrite: true
                    });
                } else {
                    motion.gsap.to(items, {
                        y: 10,
                        opacity: 0,
                        duration: motion.duration.fast * 1.2,
                        stagger: 0.02,
                        ease: motion.ease.standard,
                        overwrite: true
                    });
                }
            }

            if (window.MutationObserver) {
                var observer = new MutationObserver(sync);
                observer.observe(navMenu, { attributes: true, attributeFilter: ['class'] });
                motion.onCleanup(function () { observer.disconnect(); });
            }

            /* Leaving the drawer breakpoint must hand the items back to CSS. */
            var onBreakpoint = function (event) {
                isDrawer = event.matches;
                if (!isDrawer) releaseItems();
            };
            if (drawerQuery.addEventListener) {
                drawerQuery.addEventListener('change', onBreakpoint);
                motion.onCleanup(function () { drawerQuery.removeEventListener('change', onBreakpoint); });
            }
        }
    }

    motion.onReady(init);
})(window, document);
