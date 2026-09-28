/* =============================================================================
   RETEC MOTION — projects
   -----------------------------------------------------------------------------
   The Work section gets the strongest choreography on the page. The design is a
   filterable responsive grid, so a pinned takeover would break filtering,
   keyboard order and the scroll rhythm — instead the intensity comes from
   row-aware choreography rather than a scroll hijack.

   Ownership is split so nothing is ever animated twice:
     reveal.js   → the section heading and copy (heavier via data-motion-slow)
     images.js   → card clip, scale settle and drift (data-parallax)
     cards.js    → card tilt, lift and image zoom
     projects.js → the filter bar, the CTA, the row stagger, project hover type
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    function init() {
        if (!motion) return;

        var section = document.getElementById('work');
        if (!section) return;

        var cards = Array.prototype.slice.call(section.querySelectorAll('.work__card'));
        if (!cards.length) return;

        if (!motion.live() || !motion.gsap || !motion.ScrollTrigger) return;

        var gsap = motion.gsap;
        var ScrollTrigger = motion.ScrollTrigger;

        /* ------------------------------------------------ filters and CTA */
        var sequence = [
            { el: section.querySelector('.work__filters'), y: 12, at: 0 },
            { el: section.querySelector('.work__cta'), y: motion.reach.travel, at: 0.06 }
        ].filter(function (item) { return item.el; });

        if (sequence.length) {
            var chrome = gsap.timeline({ paused: true });
            sequence.forEach(function (item) {
                chrome.fromTo(item.el,
                    { y: item.y, opacity: 0 },
                    {
                        y: 0,
                        opacity: 1,
                        duration: motion.duration.medium * 1.4,
                        ease: motion.ease.smooth
                    },
                    item.at
                );
            });
            ScrollTrigger.create({
                trigger: sequence[0].el,
                start: 'top 90%',
                once: true,
                onEnter: function () { chrome.play(0); }
            });
        }

        /* --------------------------------------------------- card entrance
                   Each card owns its own trigger and fades in on its own as it
                   scrolls into view, instead of a whole row landing as one
                   block. The card comes up, un-masks and settles independently;
                   the grid's populating rhythm comes from the scroll position,
                   not a shared stagger. */
        cards.forEach(function (card) {
            var tween = gsap.fromTo(card,
                { y: motion.reach.lift * 2.5, opacity: 0, scale: 0.985 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: motion.duration.slow,
                    ease: motion.ease.expressive
                }
            );
            tween.pause();
            ScrollTrigger.create({
                trigger: card,
                start: 'top 88%',
                once: true,
                onEnter: function () { tween.play(0); }
            });
        });

        /* --------------------------------------------------- project hover
                   Typography only — the image is cards.js's job. */
        if (!motion.fine()) return;

        cards.forEach(function (card) {
            var titleEl = card.querySelector('.work__title');
            var meta = card.querySelector('.work__tags, .work__actions');
            var links = Array.prototype.slice.call(card.querySelectorAll('.work__link'));

            var setTitleX = titleEl ? gsap.quickTo(titleEl, 'x', { duration: 0.5, ease: 'power3.out' }) : null;
            var setMetaY = meta ? gsap.quickTo(meta, 'y', { duration: 0.5, ease: 'power3.out' }) : null;

            /* The action arrows travel on their own, slightly ahead of the
               title, so the two read as separate layers. */
            var setArrow = links.map(function (link) {
                return gsap.quickTo(link, 'x', { duration: 0.45, ease: 'power3.out' });
            });

            function onEnter() {
                if (setTitleX) setTitleX(5);
                if (setMetaY) setMetaY(-3);
                setArrow.forEach(function (move) { move(3); });
            }

            function onLeave() {
                if (setTitleX) setTitleX(0);
                if (setMetaY) setMetaY(0);
                setArrow.forEach(function (move) { move(0); });
            }

            card.addEventListener('pointerenter', onEnter);
            card.addEventListener('pointerleave', onLeave);
            card.addEventListener('pointercancel', onLeave);

            motion.onCleanup(function () {
                card.removeEventListener('pointerenter', onEnter);
                card.removeEventListener('pointerleave', onLeave);
                card.removeEventListener('pointercancel', onLeave);
                gsap.killTweensOf([titleEl, meta].concat(links).filter(Boolean));
            });
        });
    }

    motion.onReady(init);
})(window, document);
