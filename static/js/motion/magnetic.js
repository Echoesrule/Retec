/* =============================================================================
   RETEC MOTION — magnetic
   -----------------------------------------------------------------------------
   Restrained pointer attraction for `data-magnetic` elements.

   Hard constraints:
     · never more than api.reach.magnetic (10px) of travel
     · fine pointer only — no effect on touch or coarse pointers
     · off entirely under prefers-reduced-motion
     · nothing runs while idle; movement exists only inside a hover

   GSAP is the sole writer of `transform` on these elements.
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    function init() {
        if (!motion || !motion.live() || !motion.gsap) return;

        var targets = Array.prototype.slice.call(document.querySelectorAll('[data-magnetic]'));
        if (!targets.length) return;

        var gsap = motion.gsap;
        var limit = parseFloat(targets[0].getAttribute('data-magnetic')) || motion.reach.magnetic;
        var cleanups = [];

        function clamp(value, max) {
            return Math.max(-max, Math.min(max, value));
        }

        targets.forEach(function (el) {
            if (!motion.fine()) return;

            var strength = parseFloat(el.getAttribute('data-magnetic')) || limit;
            var setX = gsap.quickTo(el, 'x', { duration: 0.45, ease: 'power3.out' });
            var setY = gsap.quickTo(el, 'y', { duration: 0.45, ease: 'power3.out' });

            function onMove(event) {
                if (event.pointerType && event.pointerType !== 'mouse') return;
                var rect = el.getBoundingClientRect();
                if (!rect.width || !rect.height) return;
                var fromCentreX = (event.clientX - rect.left) / rect.width - 0.5;
                var fromCentreY = (event.clientY - rect.top) / rect.height - 0.5;
                setX(clamp(fromCentreX * strength * 2, strength));
                setY(clamp(fromCentreY * strength * 2, strength));
            }

            function onLeave() {
                setX(0);
                setY(0);
            }

            el.addEventListener('pointermove', onMove);
            el.addEventListener('pointerleave', onLeave);
            el.addEventListener('pointercancel', onLeave);
            /* Keyboard focus gets the same affordance, at a standstill. */
            var onFocus = function () { setY(-2); };
            el.addEventListener('focus', onFocus);
            el.addEventListener('blur', onLeave);

            cleanups.push(function () {
                el.removeEventListener('pointermove', onMove);
                el.removeEventListener('pointerleave', onLeave);
                el.removeEventListener('pointercancel', onLeave);
                el.removeEventListener('focus', onFocus);
                el.removeEventListener('blur', onLeave);
                gsap.killTweensOf(el);
                motion.resetTransform(el);
            });
        });

        if (cleanups.length) motion.onCleanup(function () {
            cleanups.forEach(function (fn) { fn(); });
        });
    }

    motion.onReady(init);
})(window, document);
