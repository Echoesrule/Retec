/* =============================================================================
   RETEC MOTION — core
   -----------------------------------------------------------------------------
   Owns the runtime contract every other motion module depends on:
     · environment detection (reduced motion, pointer type, viewport tier)
     · motion tokens (mirrors the CSS custom properties in variables.css)
     · GSAP plugin registration
     · Lenis smooth scroll, wired to the GSAP ticker + ScrollTrigger
     · anchor scrolling with header offset
     · a teardown registry so nothing leaks on unload / bfcache

   This module defines no UI of its own.
   ========================================================================== */
(function (window, document) {
    'use strict';

    var api = window.RETEC_MOTION || (window.RETEC_MOTION = {});
    var root = document.documentElement;

    /* ---------------------------------------------------------------- tokens
       Keep in sync with :root in static/css/variables.css */
    api.ease = {
        standard: 'power2.out',
        smooth: 'power3.out',
        expressive: 'expo.out',
        curtain: 'power3.inOut'
    };

    api.duration = {
        fast: 0.22,
        medium: 0.52,
        slow: 0.9,
        curtain: 0.62,
        liquid: 0.78
    };

    api.stagger = { sm: 0.06, md: 0.1, lg: 0.14 };

    /* Deliberately small — motion should suggest, not perform. */
    api.reach = {
        magnetic: 10,   /* px  */
        tilt: 3.2,      /* deg */
        lift: 6,        /* px  */
        travel: 18,     /* px  */
        parallax: 2.6   /* %   */
    };

    /* ------------------------------------------------------------ environment */
    var reduceQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    var fineQuery = window.matchMedia('(hover: hover) and (pointer: fine)');
    var touchQuery = window.matchMedia('(pointer: coarse)');

    api.reduced = function () { return reduceQuery.matches; };

    /* Pointer-gated interaction: the single check every hover module uses. */
    api.fine = function () {
        return fineQuery.matches && !reduceQuery.matches;
    };

    api.coarse = function () { return touchQuery.matches; };

    api.tier = function () {
        var w = window.innerWidth;
        if (w < 768) return 'mobile';
        if (w < 1200) return 'tablet';
        return 'desktop';
    };

    api.gsap = window.gsap || null;
    api.ScrollTrigger = window.ScrollTrigger || null;
    api.ScrollToPlugin = window.ScrollToPlugin || null;
    api.lenis = null;

    if (api.gsap) {
        var plugins = [api.ScrollTrigger, api.ScrollToPlugin].filter(Boolean);
        if (plugins.length) api.gsap.registerPlugin.apply(api.gsap, plugins);
    }

    if (api.ScrollTrigger) {
        /* A mobile URL bar collapsing resizes the viewport without the layout
           changing. Refreshing on that re-measures every trigger mid-scroll,
           which shows up as content stuck half-revealed. */
        api.ScrollTrigger.config({ ignoreMobileResize: true });
    }

    /* The motion system is only "live" when GSAP is present and the visitor has
       not asked for reduced motion. motion.css is scoped to this class, so the
       design renders and behaves exactly as before when it is absent. */
    var live = !!(api.gsap && !api.reduced());
    if (live) root.classList.add('retec-motion');
    api.live = function () { return root.classList.contains('retec-motion'); };

    /* -------------------------------------------------------- teardown registry */
    var cleanups = [];

    api.onCleanup = function (fn) {
        if (typeof fn === 'function') cleanups.push(fn);
        return fn;
    };

    /* The scroll-progress trigger is the one thing that drives a visual
       property, so it is preserved when reduced motion switches on mid-session
       and a dying ScrollTrigger is otherwise harmless. */
    function killScrollTriggers(keepProgress) {
        if (!api.ScrollTrigger) return;
        api.ScrollTrigger.getAll().forEach(function (trigger) {
            if (keepProgress && trigger.vars && trigger.vars.id === 'retec-scroll-progress') return;
            trigger.kill();
        });
    }

    api.destroy = function () {
        cleanups.forEach(function (fn) {
            try { fn(); } catch (error) { /* a failed teardown must not block the rest */ }
        });
        cleanups.length = 0;

        if (api.gsap) {
            api.gsap.killTweensOf('*');
            killScrollTriggers(false);
        }
        if (api.lenis) {
            api.lenis.destroy();
            api.lenis = null;
        }
    };

    /* Unload only — a bfcache restore keeps the page alive, so we re-sync there
       instead of tearing everything down. */
    window.addEventListener('pagehide', function (event) {
        if (event.persisted) return;
        api.destroy();
    });

    /* ------------------------------------------------------------- Lenis scroll */
    function startLenis() {
        if (api.lenis || api.reduced() || !window.Lenis || !api.gsap || !api.ScrollTrigger) return;

        var lenis = new window.Lenis({
            /* Weighted but responsive: 0.1 tracks the pointer closely while still
               smoothing out trackpad noise. */
            lerp: 0.1,
            wheelMultiplier: 1,
            touchMultiplier: 1.5,
            smoothWheel: true,
            /* Anchor handling belongs to api.scrollTo() so the header offset is
               respected. Letting Lenis also bind anchors would be a second
               smooth-scroll system fighting this one. */
            anchors: false
        });

        lenis.on('scroll', function () { api.ScrollTrigger.update(); });
        api.gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
        api.gsap.ticker.lagSmoothing(0);

        api.lenis = lenis;
    }

    if (live) {
        startLenis();
    }

    if (reduceQuery.addEventListener) {
        reduceQuery.addEventListener('change', function (event) {
            if (event.matches) {
                /* Honoured mid-session: drop the smooth scroll, kill scroll
                   animations and leave the content exactly as it is. */
                root.classList.remove('retec-motion');
                if (api.lenis) { api.lenis.destroy(); api.lenis = null; }
                killScrollTriggers(true);
                if (api.gsap) {
                    api.gsap.killTweensOf('*');
                    api.gsap.set('[data-motion], .retec-line__i, [data-motion="image"] img', {
                        clearProps: 'transform,opacity,clipPath,visibility,willChange'
                    });
                }
            } else {
                root.classList.add('retec-motion');
                startLenis();
                if (api.ScrollTrigger) api.ScrollTrigger.refresh();
            }
        });
    }

    /* --------------------------------------------------------- anchor scrolling */
    api.headerOffset = function () {
        var header = document.getElementById('header');
        return header ? header.offsetHeight + 8 : 0;
    };

    /* `offset` is the extra distance to leave *below* the fixed header. */
    api.scrollTo = function (target, options) {
        options = options || {};

        var node = typeof target === 'string' ? document.querySelector(target) : target;
        if (!node) return false;

        if (api.reduced() || !api.live()) {
            node.scrollIntoView({ behavior: 'auto', block: 'start' });
            return true;
        }

        var offset = options.offset == null
            ? (node.id === 'hero' ? 0 : api.headerOffset())
            : options.offset;

        if (api.lenis) {
            api.lenis.scrollTo(node, {
                offset: offset,
                duration: options.duration || 1.15,
                /* Settle rather than snap; keyboard users still get focus. */
                lock: false,
                force: true,
                onComplete: function () { if (options.onComplete) options.onComplete(); }
            });
            return true;
        }

        if (api.gsap && api.ScrollToPlugin) {
            api.gsap.to(window, {
                duration: options.duration || 0.9,
                ease: api.ease.smooth,
                scrollTo: { y: node, offsetY: offset },
                onComplete: function () { if (options.onComplete) options.onComplete(); }
            });
            return true;
        }

        node.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return true;
    };

    /* Scroll lock for the mobile menu. Falls back to body overflow when Lenis
       is not running, so the menu still locks on reduced-motion devices. */
    var lockCount = 0;
    api.setScrollLocked = function (locked) {
        if (locked) {
            lockCount += 1;
            if (api.lenis) api.lenis.stop();
            document.documentElement.classList.add('retec-scroll-locked');
        } else {
            lockCount = Math.max(0, lockCount - 1);
            if (lockCount === 0) {
                if (api.lenis) api.lenis.start();
                document.documentElement.classList.remove('retec-scroll-locked');
            }
        }
    };

    /* ------------------------------------------------------------- utilities */
    api.toArray = function (value) {
        if (!value) return [];
        if (typeof value === 'string') return Array.prototype.slice.call(document.querySelectorAll(value));
        if (value.nodeType) return [value];
        return Array.prototype.slice.call(value);
    };

    /* Hands an element's transform over to GSAP.
       GSAP parses whatever transform an element already has into its own cache
       and then composes new values on top of it. An element whose resting
       transform comes from CSS — a line parked at 110% inside its mask, the
       curtain parked below the fold, a liquid wave parked at 100% — would end
       up at 110% + 110% = 220% and simply render off-screen. Clearing first
       drops the inherited value from the cache so the tween starts from zero. */
    api.resetTransform = function (element) {
        if (!api.gsap) return;
        /* The shorthand is all GSAP accepts: `transform` is a compound that
           GSAP expands at reset time, and naming `x`/`y`/`scale` alongside it
           triggers "not eligible for reset. Try splitting into individual
           properties" — clearing them as part of `transform` is exactly what
           splitting does, so the app must not list them a second time. */
        api.gsap.set(element, { clearProps: 'transform' });
    };

    /* Reads the capped `data-motion-delay` used by the templates. */
    api.delay = function (el, fallback) {
        var raw = parseInt(el.getAttribute('data-motion-delay') || '', 10);
        if (isNaN(raw)) return fallback || 0;
        return Math.min(Math.max(raw, 0), 120) / 1000;
    };

    /* Registered-ready callbacks are fire-once: handing the *same* function in
       twice is a no-op, so a stray second registration can never double-build
       triggers or attach duplicate listeners. */
    var onReadyArmed = [];
    api.onReady = function (fn) {
        if (onReadyArmed.indexOf(fn) > -1) return;
        onReadyArmed.push(fn);
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn, { once: true });
        } else {
            fn();
        }
    };

    /* ---------------------------------------------------------- reveal gate
       loader.js resolves this the moment the page is uncovered. Modules that
       must play *underneath* the loader (the hero) wait on it; scroll-driven
       work never does, because it is independent of the entrance.

       The watchdog guarantees resolution even if the loader never runs, so no
       entrance animation can be left stranded at opacity 0. */
    api.ready = new Promise(function (resolve) {
        api._resolveReady = resolve;
    });

    api.whenReady = function (fn) {
        api.ready.then(fn);
    };

    api.markReady = function () {
        if (!api._resolveReady) return;
        var resolve = api._resolveReady;
        api._resolveReady = null;
        resolve();
    };

    api.onReady(function () {
        /* Failsafe only — loader.js resolves this when the loader finishes.
           The budget has to outlast the loader's own worst case (MAX_VISIBLE
           2.2s plus the curtain exit) so an entrance can never stay stranded
           at opacity 0 if the loader never reports back. */
        window.setTimeout(api.markReady, 3800);
    });

    /* bfcache / history restores need the scroll-linked layer re-measured. */
    window.addEventListener('pageshow', function () {
        if (api.lenis) api.lenis.resize();
        if (api.ScrollTrigger) api.ScrollTrigger.refresh();
    });

    /* --------------------------------------------------------- font settling
       Every trigger is built at DOMContentLoaded — before the webfonts deliver
       their final metrics — so a cold first load measures short where a warm
       refresh measures right. That asymmetry is the first-load-vs-refresh bug.
       ScrollTrigger already auto-refreshes on 'load' (its default
       autoRefreshEvents); fonts are the one signal it never listens for, so we
       refresh exactly once here and nowhere else. */
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () {
            if (api.ScrollTrigger) api.ScrollTrigger.refresh();
        });
    }
})(window, document);
