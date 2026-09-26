/* =============================================================================
   RETEC MOTION — reveal
   -----------------------------------------------------------------------------
   Reusable ScrollTrigger reveals. Content type drives the motion, so a section
   never feels like one long undifferentiated fade:

     heading  → masked line reveal (overflow-clipped, translateY 110% → 0)
     text     → translateY + opacity
     label    → short travel, fades slightly ahead of the copy
     card     → single unit, slight scale, never split into lines

   Markup contract:  data-motion="reveal|heading|text|label|stagger|card|image"
                     data-motion-delay="<ms, capped at 120>"
   ========================================================================== */
(function (window, document) {
    'use strict';

    /* core.js always runs first (defer order) and publishes the api, so
       this is one shared live reference for the whole module. */
    var motion = window.RETEC_MOTION;

    var HEADING_SELECTOR = 'h1, h2, h3, h4, .section__title, .testimonials__title';
    var TEXT_SELECTOR = 'p, a, ul, ol, dl, blockquote, figure, table, address';
    var LABEL_PATTERN = /(^|__)(eyebrow|kicker|label|tagline|overline)$/;
    var MAX_DELAY = 0.12;

    /* ------------------------------------------------------- masked line split
       Rows are delimited by <br>, so the existing heading markup, imagery and
       per-word styling inside each row are preserved untouched. */
    function splitLines(el) {
        if (el.getAttribute('data-retec-split') === 'done') {
            return Array.prototype.slice.call(el.querySelectorAll(':scope > .retec-line'));
        }

        var rows = [[]];
        Array.prototype.slice.call(el.childNodes).forEach(function (node) {
            if (node.nodeType === 1 && node.tagName === 'BR') {
                rows.push([]);
                return;
            }
            rows[rows.length - 1].push(node);
        });

        var lines = [];
        rows.forEach(function (nodes) {
            if (!nodes.length) return;
            var line = document.createElement('span');
            var inner = document.createElement('span');
            line.className = 'retec-line';
            inner.className = 'retec-line__i';
            nodes.forEach(function (node) { inner.appendChild(node); });
            line.appendChild(inner);
            el.appendChild(line);
            lines.push(inner);
        });

        el.setAttribute('data-retec-split', 'done');
        return lines;
    }

    /* -------------------------------------------------------- unit collection
       Turns a marked root into a flat, ordered list of animation units. */
    function collectUnits(root, kind) {
        var units = [];
        var claimed = [];

        function isClaimed(el) {
            return claimed.some(function (taken) { return taken === el || taken.contains(el); });
        }

        function push(el, type) {
            if (!el || el.nodeType !== 1 || isClaimed(el)) return;
            claimed.push(el);
            units.push({ el: el, type: type });
        }

        if (kind === 'heading' || kind === 'card') {
            push(root, kind);
            return units;
        }

        if (kind === 'text' || kind === 'label') {
            push(root, kind);
            return units;
        }

        if (kind === 'stagger') {
            Array.prototype.forEach.call(root.children, function (child) {
                push(child, 'text');
            });
            return units;
        }

        /* kind === 'reveal' — compose the motion from the content itself. */
        Array.prototype.forEach.call(root.querySelectorAll(HEADING_SELECTOR), function (heading) {
            push(heading, 'heading');
        });

        Array.prototype.forEach.call(root.querySelectorAll(TEXT_SELECTOR), function (block) {
            if (block.closest(HEADING_SELECTOR)) return;
            push(block, LABEL_PATTERN.test(block.className || '') ? 'label' : 'text');
        });

        /* Lists read better when their items rise in a tight sequence. */
        units.forEach(function (unit) {
            if (unit.type === 'text' && /^(UL|OL)$/.test(unit.el.tagName) && unit.el.children.length) {
                unit.type = 'list';
            }
        });

        /* A root that is itself the content (a lone <p>, <a>, …). */
        if (!units.length) push(root, 'text');

        return units;
    }

    /* ---------------------------------------------------------------- tweens
       `scale` lets a section ask for more weight without a second code path —
       the Work heading uses it, everything else stays at 1. */
    function tweenFor(gsap, motion, unit, scale) {
        if (unit.type === 'heading') {
            var lines = splitLines(unit.el);
            if (!lines.length) return null;
            /* Park the mask in JS rather than CSS: a CSS transform would be
               parsed into GSAP's cache and compounded with the from-state, and
               a tween that never runs would leave the heading clipped. */
            motion.resetTransform(lines);
            gsap.set(lines, { yPercent: 110, opacity: 0 });
            return gsap.to(lines,
                {
                    yPercent: 0,
                    opacity: 1,
                    duration: motion.duration.medium * 1.6 * scale,
                    stagger: motion.stagger.md * scale,
                    ease: motion.ease.expressive
                }
            );
        }

        if (unit.type === 'label') {
            return gsap.fromTo(unit.el,
                { y: 6, opacity: 0 },
                { y: 0, opacity: 1, duration: motion.duration.medium * scale, ease: motion.ease.standard }
            );
        }

        if (unit.type === 'list') {
            return gsap.fromTo(unit.el.children,
                { y: 12, opacity: 0 },
                {
                    y: 0,
                    opacity: 1,
                    duration: motion.duration.medium * scale,
                    stagger: motion.stagger.sm * scale,
                    ease: motion.ease.standard
                }
            );
        }

        if (unit.type === 'card') {
            return gsap.fromTo(unit.el,
                { y: motion.reach.lift * 2, opacity: 0, scale: 0.985 },
                {
                    y: 0,
                    opacity: 1,
                    scale: 1,
                    duration: motion.duration.slow * scale,
                    ease: motion.ease.expressive
                }
            );
        }

        return gsap.fromTo(unit.el,
            { y: motion.reach.travel, opacity: 0 },
            {
                y: 0,
                opacity: 1,
                duration: motion.duration.medium * 1.35 * scale,
                ease: motion.ease.smooth
            }
        );
    }

    /* Gap inserted after each unit so the sequence reads as choreography
       rather than a single block of motion. */
    function gapAfter(unit, scale) {
        if (unit.type === 'heading') return 0.1 * scale;
        if (unit.type === 'label') return 0.02;
        if (unit.type === 'card') return 0.05;
        return 0.07;
    }

    /* Marks a root as revealed. Also stamps the enclosing motion root, because
       the CSS that un-parks a masked line keys off that attribute, and a tall
       root reveals its units individually. */
    function markRevealed(el) {
        if (!el) return;
        el.setAttribute('data-motion-revealed', '');
        var root = el.closest ? el.closest('[data-motion]') : null;
        if (root && root !== el) root.setAttribute('data-motion-revealed', '');
    }

    /* Hands content back to the browser. Only ever touches an element that is
       genuinely still hidden, so it can never strip a transform an interaction
       module has since claimed. */
    function release(elements) {
        elements.forEach(function (el) {
            if (!el) return;
            var opacity = parseFloat(window.getComputedStyle(el).opacity);
            if (!isNaN(opacity) && opacity > 0.98) {
                markRevealed(el);
                return;
            }
            el.style.removeProperty('opacity');
            el.style.removeProperty('visibility');
            el.style.removeProperty('transform');
            /* A heading's lines are masked individually, so clearing the
               heading's own styles is not enough to un-park them. */
            var lines = el.querySelectorAll('.retec-line__i');
            Array.prototype.forEach.call(lines, function (line) {
                line.style.transform = 'none';
            });
            markRevealed(el);
        });
    }

    function init() {
        if (!motion) return;

        var roots = Array.prototype.slice.call(document.querySelectorAll('[data-motion]'))
            .filter(function (el) { return el.getAttribute('data-motion') !== 'image'; });

        if (!roots.length) return;

        /* Content is visible by default. GSAP only takes the initial state away
           once we know a trigger exists, so a failure can never hide the page. */
        if (!motion.live() || !motion.gsap || !motion.ScrollTrigger) {
            roots.forEach(function (el) { el.setAttribute('data-motion-revealed', ''); });
            return;
        }

        var gsap = motion.gsap;
        var ScrollTrigger = motion.ScrollTrigger;
        var guarded = [];
        var created = 0;

        function reveal(unit, tween, delay) {
            tween.eventCallback('onComplete', function () { markRevealed(unit.el); });
            if (delay) gsap.delayedCall(delay, function () { tween.play(0); });
            else tween.play(0);
        }

        try {
            roots.forEach(function (root) {
                var kind = root.getAttribute('data-motion');
                var units = collectUnits(root, kind);
                if (!units.length) return;

                var scale = root.hasAttribute('data-motion-slow') ? 1.35 : 1;
                var delay = motion.delay(root, 0);
                units.forEach(function (unit) { guarded.push(unit.el); });

                /* Compact root: one sequence, one trigger. Tall root: each unit
                   reveals on its own so nothing finishes before it is scrolled to. */
                var isTall = root.offsetHeight > window.innerHeight * 1.15;

                if (isTall && units.length > 1) {
                    units.forEach(function (unit) {
                        var tween = tweenFor(gsap, motion, unit, scale);
                        if (!tween) return;
                        tween.pause(0);
                        ScrollTrigger.create({
                            trigger: unit.el,
                            start: 'top 90%',
                            once: true,
                            onEnter: function () { reveal(unit, tween, delay); }
                        });
                        created += 1;
                    });
                    return;
                }

                var timeline = gsap.timeline({ paused: true });
                var cursor = 0;
                units.forEach(function (unit) {
                    var at = cursor;
                    cursor += gapAfter(unit, scale);
                    timeline.add(tweenFor(gsap, motion, unit, scale), at);
                });
                timeline.eventCallback('onComplete', function () { markRevealed(root); });

                ScrollTrigger.create({
                    trigger: root,
                    start: 'top 88%',
                    once: true,
                    onEnter: function () {
                        if (delay) gsap.delayedCall(delay, function () { timeline.play(0); });
                        else timeline.play(0);
                    }
                });
                created += 1;
            });
        } catch (error) {
            created = 0;
            if (window.console) window.console.warn('[retec-motion] reveal init failed', error);
        }

        if (!created) {
            release(guarded);
            return;
        }

        /* Last-resort watchdog: anything still hidden but already on screen is
           handed back rather than left invisible. */
        var watchdog = window.setTimeout(function () {
            var viewport = window.innerHeight;
            guarded.forEach(function (el) {
                if (!el || el.getAttribute('data-motion-revealed')) return;
                var rect = el.getBoundingClientRect();
                if (rect.top < viewport * 0.98 && rect.bottom > 0) release([el]);
            });
        }, 4000);

        motion.onCleanup(function () { window.clearTimeout(watchdog); });
    }

    motion.onReady(init);
})(window, document);
