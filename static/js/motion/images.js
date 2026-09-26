/* =============================================================================
   RETEC MOTION — images
   -----------------------------------------------------------------------------
   Viewport entrances for imagery: an overflow-clipped reveal plus a small
   scale settle. `data-parallax` adds a restrained, scroll-linked drift on top.

   The resting scale deliberately stops at 1.04 rather than 1 so the parallax
   travel can never expose an edge. Movement stays inside the 5–10% band.
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    var RESTING_SCALE = 1.04;
    var REVEAL_SCALE = 1.12;
    var CLIP_FROM = 'inset(7% 5% 0 5%)';
    var CLIP_TO = 'inset(0% 0% 0% 0%)';

    function mediaOf(el) {
        return el.matches('img') ? el : el.querySelector('img');
    }

    function init() {
        if (!motion) return;

        var frames = Array.prototype.slice.call(document.querySelectorAll('[data-motion="image"]'));
        if (!frames.length) return;

        if (!motion.live() || !motion.gsap || !motion.ScrollTrigger) {
            frames.forEach(function (frame) {
                var media = mediaOf(frame);
                if (media) media.style.removeProperty('transform');
            });
            return;
        }

        var gsap = motion.gsap;
        var canParallax = motion.tier() === 'desktop' && !motion.coarse();

        frames.forEach(function (frame) {
            var media = mediaOf(frame);
            if (!media) return;

            var wantsParallax = canParallax && frame.hasAttribute('data-parallax');
            var resting = wantsParallax ? RESTING_SCALE : 1;

            /* Published so cards.js can restore the correct value on mouse-out
               instead of assuming a number. */
            media.setAttribute('data-resting-scale', String(resting));

            /* Clip travels on the frame, scale + drift on the media. */
            gsap.set(media, { transformOrigin: 'center center' });

            var intro = gsap.fromTo(frame,
                { clipPath: CLIP_FROM },
                {
                    clipPath: CLIP_TO,
                    duration: motion.duration.slow * 1.1,
                    ease: motion.ease.expressive,
                    scrollTrigger: {
                        trigger: frame,
                        start: 'top 92%',
                        once: true
                    }
                }
            );

            var settle = gsap.fromTo(media,
                { scale: REVEAL_SCALE },
                {
                    scale: resting,
                    duration: motion.duration.slow * 1.2,
                    ease: motion.ease.expressive,
                    scrollTrigger: {
                        trigger: frame,
                        start: 'top 92%',
                        once: true
                    }
                }
            );

            if (!wantsParallax) return;

            /* Scroll-linked drift, capped well inside the allowed range. */
            var drift = gsap.fromTo(media,
                { yPercent: -motion.reach.parallax },
                {
                    yPercent: motion.reach.parallax,
                    ease: 'none',
                    scrollTrigger: {
                        trigger: frame,
                        start: 'top bottom',
                        end: 'bottom top',
                        scrub: true
                    }
                }
            );
        });
    }

    motion.onReady(init);
})(window, document);
