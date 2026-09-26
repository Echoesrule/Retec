/* =============================================================================
   RETEC MOTION — liquid button
   -----------------------------------------------------------------------------
   The signature RETEC CTA. A monochrome colour inversion driven by a single
   liquid sweep: on hover the opposite colour physically flows left→right across
   the button and the surface underneath is inverted.

     · a dark CTA  → WHITE liquid sweeps in, the covered surface reads white
                     with ink text/arrow
     · a light CTA → INK   liquid sweeps in, the covered surface reads ink
                     with white text/arrow  (`data-liquid-theme="light"`)

   Contrast stays clean for the whole sweep, not just at the end: the text is
   double-layered. A mirrored copy of the content, already in the filled colour,
   travels in lockstep with the liquid, so the glyphs over the filled region are
   always correct and the glyphs over the unfilled region keep their resting
   colour. No gradients, glow, colours or looping wave motion — the only moving
   parts are the two liquid layers (both monochrome) and a 4–6px arrow nudge.

   Markup contract (unchanged from the design):
     <a data-liquid>
       <span class="hero-editorial__liquid">
         <svg class="hero-editorial__liquid-wave hero-editorial__liquid-wave--back">…</svg>
         <svg class="hero-editorial__liquid-wave">…</svg>
       </span>
       <span class="hero-editorial__btn-content">…<span data-liquid-arrow>↗</span></span>
     </a>

   The mirrored text layer is built here at runtime, never in the template.
   Failsafe: motion.css parks every liquid layer off-axis by default, so with
   reduced motion or no GSAP the CTA is simply its plain monochrome self.
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    var SWEEP = 0.55;   /* s  — left→right fill travel (spec: 500–650ms) */
    var DRAIN = 0.5;    /* s  — reverse; a fraction quicker reads tactile */
    var LEAD = 0.05;    /* s  — faint back layer trails the opaque front,
                               the subtle depth behind the leading edge  */
    var ARROW_TRAVEL = 4; /* px — nudge, held inside the 4–6px band */

    function buildInvert(el, content) {
        /* A second copy of the text in the filled colour, masked to exactly
           where the liquid already is by riding the same xPercent as the
           front wave. Arrow is excluded — it inverts in place instead. */
        var clone = content.cloneNode(true);
        var arrow = clone.querySelector('[data-liquid-arrow]');
        if (arrow && arrow.parentNode) arrow.parentNode.removeChild(arrow);

        var wrap = document.createElement('span');
        wrap.className = 'hero-editorial__liquid-invert';
        wrap.setAttribute('aria-hidden', 'true');
        wrap.appendChild(clone);

        var liquid = el.querySelector('.hero-editorial__liquid');
        if (liquid) liquid.appendChild(wrap);
        return wrap;
    }

    function init() {
        if (!motion) return;

        var buttons = Array.prototype.slice.call(document.querySelectorAll('[data-liquid]'));
        if (!buttons.length) return;

        var gsap = motion.live() ? motion.gsap : null;
        var cleanups = [];

        buttons.forEach(function (el) {
            var waves = Array.prototype.slice.call(el.querySelectorAll('.hero-editorial__liquid-wave'));
            if (!waves.length) return;

            var arrow = el.querySelector('[data-liquid-arrow]');
            var front = waves[waves.length - 1];   /* opaque layer, on top  */
            var back = waves[0];                   /* faint layer, trails   */

            /* Reduced motion or no GSAP: CSS keeps every layer parked off the
               button, so the CTA stays its plain monochrome self. */
            if (!gsap) return;

            /* Touch and coarse pointers get no pointer-driven fill and no
               mirrored layer; the design keeps its resting surface, with the
               subtle press state coming from CSS. */
            if (!motion.fine()) return;

            var content = el.querySelector('.hero-editorial__btn-content');
            var invert = content ? buildInvert(el, content) : null;
            var group = [front, back, invert].filter(Boolean);

            var arrowRest = null;
            var arrowFill = null;
            if (arrow) {
                arrowRest = window.getComputedStyle(el).color;
                arrowFill = (window.getComputedStyle(el).getPropertyValue('--lt-ink') || '').trim() || arrowRest;
            }

            /* Clear the CSS failsafe park from GSAP's cache first, then park
               identically in JS so the sweep owns the horizontal travel. */
            motion.resetTransform(group);
            gsap.set(group, { xPercent: -100 });

            function killActive() {
                gsap.killTweensOf(group);
                if (arrow) gsap.killTweensOf(arrow);
            }

            function sweep() {
                var tl = gsap.timeline({ defaults: { ease: motion.ease.smooth } });
                if (invert) tl.to(invert, { xPercent: 0, duration: SWEEP }, 0);
                tl.to(front, { xPercent: 0, duration: SWEEP }, 0);
                tl.to(back, { xPercent: 0, duration: SWEEP }, LEAD);
                return tl;
            }

            function drain() {
                return gsap.timeline({ defaults: { ease: motion.ease.smooth } })
                    .to(group, { xPercent: -100, duration: DRAIN }, 0);
            }

            function onEnter() {
                killActive();
                sweep();
                if (!arrow) return;
                gsap.to(arrow, {
                    x: ARROW_TRAVEL,
                    y: -ARROW_TRAVEL,
                    duration: motion.duration.medium,
                    ease: motion.ease.expressive
                });
                /* The arrow sits at the far end of the text, so its colour flips
                   only once the liquid has nearly arrived — timing it with the
                   sweep start would leave it mid-flip over the unfilled half. */
                gsap.to(arrow, {
                    color: arrowFill,
                    duration: motion.duration.fast,
                    ease: motion.ease.standard,
                    delay: SWEEP * 0.55
                });
            }

            function onLeave() {
                killActive();
                drain();
                if (!arrow) return;
                gsap.to(arrow, {
                    x: 0,
                    y: 0,
                    duration: motion.duration.medium,
                    ease: motion.ease.expressive
                });
                gsap.to(arrow, {
                    color: arrowRest,
                    duration: motion.duration.fast,
                    ease: motion.ease.standard,
                    delay: DRAIN * 0.5
                });
            }

            el.addEventListener('pointerenter', onEnter);
            el.addEventListener('pointerleave', onLeave);
            el.addEventListener('focus', onEnter);
            el.addEventListener('blur', onLeave);

            cleanups.push(function () {
                el.removeEventListener('pointerenter', onEnter);
                el.removeEventListener('pointerleave', onLeave);
                el.removeEventListener('focus', onEnter);
                el.removeEventListener('blur', onLeave);
                gsap.killTweensOf(group);
                if (arrow) gsap.killTweensOf(arrow);
            });
        });

        if (cleanups.length) motion.onCleanup(function () {
            cleanups.forEach(function (fn) { fn(); });
        });
    }

    motion.onReady(init);
})(window, document);