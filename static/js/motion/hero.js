/* =============================================================================
   RETEC MOTION — hero
   -----------------------------------------------------------------------------
   The existing hero, sequenced. Nothing about the design changes: the same
   elements simply arrive in a considered order instead of all at once.

     1  backdrop (image panel + washes)
     2  eyebrow / trust pill
     3  headline  ← masked upward reveal
     4  description
     5  social proof metadata
     6  primary CTA
     7  secondary CTA
     8  floating stat / project card / chips
     9  client bar

   Waits for the loader (if one ran) so the hero plays underneath it, and for
   the hero image so the panel never animates around an empty box.
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    function init() {
        if (!motion || !motion.live() || !motion.gsap) return;

        var hero = document.getElementById('hero');
        if (!hero) return;

        var gsap = motion.gsap;
        hero.classList.add('hero--animating');

        var pick = function (selector) { return hero.querySelector(selector); };

        var backdrop = [
            pick('.hero-editorial__panel'),
            pick('.hero-editorial__stat'),
            pick('.hero-editorial__card'),
            pick('.hero-editorial__chip')
        ].filter(Boolean);

        var sequence = [
            { el: pick('.hero-editorial__pill'), y: 14 },
            { el: pick('.hero-editorial__title'), y: 0, mask: true },
            { el: pick('.hero-editorial__desc'), y: 20 },
            { el: pick('.hero-editorial__social'), y: 18 },
            { el: pick('.hero-editorial__actions'), y: 18 },
            { el: pick('.hero-editorial__logos'), y: 14 }
        ];

        function build() {
            var timeline = gsap.timeline({ defaults: { ease: motion.ease.expressive } });

            /* 1 — backdrop */
            timeline.fromTo(backdrop,
                { autoAlpha: 0, scale: 0.965, y: 14 },
                {
                    autoAlpha: 1,
                    scale: 1,
                    y: 0,
                    duration: motion.duration.slow * 1.25,
                    stagger: motion.stagger.md,
                    ease: motion.ease.smooth
                },
                0
            );

            /* 2–7 — copy, headline masked */
            sequence.forEach(function (item, index) {
                if (!item.el) return;
                var at = 0.1 + index * 0.075;
                timeline.fromTo(item.el,
                    item.mask
                        ? { yPercent: 108, opacity: 0 }
                        : { y: item.y, opacity: 0 },
                    item.mask
                        ? { yPercent: 0, opacity: 1, duration: motion.duration.medium * 1.7 }
                        : { y: 0, opacity: 1, duration: motion.duration.medium * 1.4 },
                    at
                );
            });

            /* Any remaining editorial reveals ride just behind the CTA. */
            hero.querySelectorAll('.hero-editorial__reveal').forEach(function (el) {
                if (sequence.some(function (item) { return item.el === el; })) return;
                if (backdrop.indexOf(el) !== -1) return;
                timeline.fromTo(el,
                    { y: 16, opacity: 0 },
                    { y: 0, opacity: 1, duration: motion.duration.medium * 1.4 },
                    0.42
                );
            });

            return timeline;
        }

        /* Two independent gates: the hero image must be decoded so the panel
           reveal never plays around an empty box, and the loader (if any) must
           have uncovered the page. Both are individually time-bounded, so a
           slow connection or a missing image can never strand the entrance. */
        var img = pick('.hero-editorial__img');
        var imageSettled = !img || img.complete;
        var loaderSettled = false;
        var started = false;

        if (img && !img.complete) {
            var release = function () { imageSettled = true; maybeStart(); };
            img.addEventListener('load', release, { once: true });
            img.addEventListener('error', release, { once: true });
            var imageTimeout = window.setTimeout(release, 900);
            motion.onCleanup(function () { window.clearTimeout(imageTimeout); });
        }

        motion.whenReady(function () {
            loaderSettled = true;
            maybeStart();
        });

        function maybeStart() {
            if (started || !imageSettled || !loaderSettled) return;
            started = true;

            var timeline = build();
            timeline.play(0);
            timeline.eventCallback('onComplete', function () {
                hero.classList.remove('hero--animating');
            });
        }
    }

    motion.onReady(init);
})(window, document);
