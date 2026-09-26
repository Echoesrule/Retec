/* =============================================================================
   RETEC MOTION — loader
   -----------------------------------------------------------------------------
   Two distinct pieces of chrome, deliberately kept apart:

     .retec-page-loader  branded first-load loader: RETEC wordmark revealed
                         character by character, a hairline progress track and
                         an optional percentage. Only on a genuine first visit.

     .retec-curtain      the page-transition wipe. No wordmark, no progress —
                         just the studio mark sliding under a full-bleed panel.

   Rules the loader must never break:
     · never artificially delay a fast load (progress is driven by real signals)
     · never appear for anchor navigation
     · never trap the page if anything goes wrong (hard failsafe below)
     · under reduced motion, nothing shows at all
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    var SESSION_KEY = 'retec:seen';
    var TRANSITION_KEY = 'retec:transition';
    var MIN_VISIBLE = 0.45;   /* s — the only deliberate floor, so the exit reads */
    var MAX_VISIBLE = 2.2;    /* s — absolute ceiling on the whole entrance     */

    function splitWordmark(mark) {
        var text = (mark.textContent || '').trim();
        mark.textContent = '';
        var chars = [];
        text.split('').forEach(function (character) {
            var span = document.createElement('span');
            span.className = 'retec-page-loader__char';
            span.textContent = character === ' ' ? '\u00a0' : character;
            mark.appendChild(span);
            chars.push(span);
        });
        return chars;
    }

    function init() {
        var root = document.documentElement;
        var loader = document.querySelector('.retec-page-loader');
        var curtain = document.querySelector('.retec-curtain');

        /* Reduced motion: reveal immediately, show nothing. */
        if (motion && motion.reduced()) {
            root.classList.remove('retec-motion-boot');
            if (loader) loader.parentNode.removeChild(loader);
            if (curtain) curtain.parentNode.removeChild(curtain);
            if (motion) motion.markReady();
            return;
        }

        var isFirstVisit = false;
        try {
            isFirstVisit = !window.sessionStorage.getItem(SESSION_KEY);
            window.sessionStorage.setItem(SESSION_KEY, '1');
        } catch (error) {
            /* Private mode: fall back to "assume first visit" only if the boot
               gate is actually in play, so a repeat visit is never interrupted. */
            isFirstVisit = root.classList.contains('retec-motion-boot');
        }

        var cameBackFromTransition = false;
        try {
            cameBackFromTransition = window.sessionStorage.getItem(TRANSITION_KEY) === '1';
            window.sessionStorage.removeItem(TRANSITION_KEY);
        } catch (error) { /* storage unavailable — treat as a normal load */ }
        var gsap = motion && motion.live() ? motion.gsap : null;
        var shownAt = Date.now();
        var released = false;
        var entranceDone = !gsap;
        var progressDone = !gsap;
        var tweens = [];
        var paint = function () {};

        /* ------------------------------------------------- branded first load
           Shown only on a genuine first visit of the session, and never for an
           anchor jump. Progress is honest: it eases toward "almost ready" and
           only lands on 100 once the document actually has. */
        var loaderActive = !!(loader && isFirstVisit && !cameBackFromTransition);
        var ramp = null;

        if (loaderActive && gsap) {
            var mark = loader.querySelector('.retec-page-loader__wordmark');
            var bar = loader.querySelector('.retec-page-loader__bar');
            var count = loader.querySelector('.retec-page-loader__count');
            var progress = { value: 0 };

            paint = function (value) {
                var pct = Math.max(0, Math.min(100, Math.round(value)));
                if (bar) bar.style.transform = 'scaleX(' + (pct / 100) + ')';
                if (count) count.textContent = pct + '%';
            };
            paint(0);

            var chars = mark ? splitWordmark(mark) : [];
            var entrance = gsap.timeline({
                onComplete: function () {
                    entranceDone = true;
                    attemptRelease();
                }
            });

            if (chars.length) {
                entrance.fromTo(chars,
                    { yPercent: 118, opacity: 0 },
                    {
                        yPercent: 0,
                        opacity: 1,
                        duration: 0.62,
                        stagger: 0.045,
                        ease: motion.ease.expressive
                    },
                    0
                );
            }

            ramp = gsap.to(progress, {
                value: 92,
                duration: 0.95,
                ease: motion.ease.smooth,
                onUpdate: function () { paint(progress.value); }
            });
            tweens.push(ramp);

            if (motion) motion.loaderPaint = paint;
        } else {
            root.classList.remove('retec-motion-boot');
        }

        /* ------------------------------------------------ transition curtain */
        if (curtain && gsap) {
            /* The parked offset lives in JS. CSS used to declare 100% here,
               which GSAP parsed into its cache and then compounded with its own
               yPercent, so the incoming wipe never uncovered the page. */
            motion.resetTransform(curtain);

            if (cameBackFromTransition) {
                gsap.set(curtain, { yPercent: 0, autoAlpha: 1 });
                tweens.push(gsap.to(curtain, {
                    yPercent: -101,
                    duration: motion.duration.curtain,
                    ease: motion.ease.curtain,
                    onComplete: function () { gsap.set(curtain, { autoAlpha: 0 }); }
                }));
            } else {
                /* Parked and invisible; page-transitions.js brings it back. */
                gsap.set(curtain, { yPercent: 101, autoAlpha: 0 });
            }
        }

        /* ------------------------------------------------------------ release */
        function attemptRelease() {
            if (released || !entranceDone || !progressDone) return;
            release();
        }

        function settle() {
            if (!loaderActive || !gsap) {
                progressDone = true;
                attemptRelease();
                return;
            }
            if (progressDone) return;

            var finish = { value: 0 };
            if (ramp) { ramp.kill(); ramp = null; }
            paint(92);

            tweens.push(gsap.to(finish, {
                value: 1,
                duration: 0.3,
                ease: 'power2.out',
                onUpdate: function () { paint(92 + finish.value * 8); },
                onComplete: function () {
                    progressDone = true;
                    attemptRelease();
                }
            }));
        }

        function release() {
            if (released) return;
            released = true;

            /* The only deliberate floor: long enough for the exit to read as a
               wipe, short enough that a fast load is never held back. */
            var elapsed = (Date.now() - shownAt) / 1000;
            var wait = Math.max(0, MIN_VISIBLE - elapsed);

            function finish() {
                root.classList.remove('retec-motion-boot');
                root.classList.add('retec-motion-boot-done');
                /* Take the node out entirely. It is a one-shot entrance, and a
                   full-viewport fixed layer left in the document keeps a
                   compositing layer and pointer-events alive for the rest of
                   the session. The curtain is deliberately kept — page
                   transitions reuse it. */
                if (loader && loader.parentNode) loader.parentNode.removeChild(loader);
                if (motion) motion.markReady();
            }

            var exit = loaderActive && gsap
                ? gsap.to(loader, {
                    yPercent: -101,
                    duration: motion.duration.curtain,
                    delay: wait,
                    ease: motion.ease.curtain,
                    onComplete: finish
                })
                : null;

            if (!exit) {
                if (wait > 0) window.setTimeout(finish, wait * 1000);
                else finish();
            }
        }

        /* Release once the document is parsed and the entrance has had room to
           settle — *not* on window load. Waiting on every eager image and font
           on a cold pipe is what let the boot gate (templates/base.html, 2.2s)
           fail the loader over on a first visit. A fast load still settles as
           soon as 'load' arrives; the budget just stops a slow one from being
           able to strand the reveal. settle() is idempotent, so whichever path
           runs first wins and the ceiling below remains the hard failsafe. */
        var settleBudget = null;
        function settleSoon() {
            window.clearTimeout(settleBudget);
            settleBudget = null;
            settle();
        }
        settleBudget = window.setTimeout(settleSoon, 1000);
        if (document.readyState === 'complete') {
            settleSoon();
        } else {
            window.addEventListener('load', settleSoon, { once: true });
        }

        /* Ceiling: a stalled sub-resource must never hold the page hostage. */
        var ceiling = window.setTimeout(release, MAX_VISIBLE * 1000);

        /* bfcache restore: drop every layer of chrome instantly. */
        window.addEventListener('pageshow', function (event) {
            if (!event.persisted) return;
            window.clearTimeout(ceiling);
            tweens.forEach(function (tween) { if (tween) tween.kill(); });
            root.classList.remove('retec-motion-boot');
            root.classList.add('retec-motion-boot-done');
            if (loader && loader.parentNode) loader.parentNode.removeChild(loader);
            if (motion) motion.markReady();
        });

        if (motion) {
            motion.onCleanup(function () {
                window.clearTimeout(ceiling);
                tweens.forEach(function (tween) { if (tween) tween.kill(); });
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})(window, document);
