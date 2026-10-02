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

        /* -------------------------------------------- homepage section state */
        if (document.body.classList.contains('home-page') && navMenu) {
            var navList = navMenu.querySelector('.nav__list');
            var sectionLinks = navLinks.filter(function (link) {
                return link.hasAttribute('data-nav-section');
            });
            var sections = sectionLinks.map(function (link) {
                var id = link.getAttribute('data-nav-section');
                var node = document.getElementById(id);
                return node ? { id: id, node: node, link: link, intersecting: false } : null;
            }).filter(Boolean);

            if (navList && sections.length && window.IntersectionObserver) {
                var desktopQuery = window.matchMedia('(min-width: 769px)');
                var indicatorHost = document.createElement('li');
                indicatorHost.className = 'nav__indicator-host';
                indicatorHost.setAttribute('aria-hidden', 'true');

                var activeIndicator = document.createElement('span');
                activeIndicator.className = 'nav__active-indicator';
                var hoverIndicator = document.createElement('span');
                hoverIndicator.className = 'nav__hover-indicator';
                indicatorHost.appendChild(activeIndicator);
                indicatorHost.appendChild(hoverIndicator);
                navList.insertBefore(indicatorHost, navList.firstChild);

                var sectionObserver;
                var activeSection = null;
                var hoveredLink = null;
                var pendingSectionId = null;
                var pendingTimer = null;
                var resizeFrame = 0;
                var indicatorGsap = motion.live() ? motion.gsap : null;

                function findSection(id) {
                    for (var i = 0; i < sections.length; i += 1) {
                        if (sections[i].id === id) return sections[i];
                    }
                    return null;
                }

                function moveIndicator(indicator, link, visible, animate, padding) {
                    if (!desktopQuery.matches || !link) return;

                    var listRect = navList.getBoundingClientRect();
                    var linkRect = link.getBoundingClientRect();
                    var width = linkRect.width + padding * 2;
                    var x = linkRect.left - listRect.left - padding;
                    var y = linkRect.top - listRect.top + linkRect.height / 2;
                    var scaleY = indicator === activeIndicator ? 1.04 : 1.02;

                    if (indicatorGsap) {
                        if (!animate) {
                            indicatorGsap.set(indicator, {
                                x: x,
                                y: y,
                                yPercent: -50,
                                scaleX: width,
                                scaleY: scaleY,
                                autoAlpha: visible ? 1 : 0,
                                transformOrigin: 'left center'
                            });
                            return;
                        }

                        indicatorGsap.to(indicator, {
                            x: x,
                            y: y,
                            scaleX: width,
                            scaleY: scaleY,
                            autoAlpha: visible ? 1 : 0,
                            duration: visible ? 0.44 : 0.26,
                            ease: visible ? 'back.out(1.16)' : 'power2.out',
                            overwrite: 'auto'
                        });
                        return;
                    }

                    indicator.style.left = x + 'px';
                    indicator.style.top = y + 'px';
                    indicator.style.width = width + 'px';
                    indicator.style.transform = 'translateY(-50%) scaleY(' + scaleY + ')';
                    indicator.style.opacity = visible ? '1' : '0';
                    indicator.style.visibility = visible ? 'visible' : 'hidden';
                }

                function setActiveSection(id, animate) {
                    var next = findSection(id);
                    if (!next) return;
                    var changed = activeSection !== next;

                    sections.forEach(function (section) {
                        var active = section === next;
                        section.link.classList.toggle('nav__link--active', active);
                        if (active) section.link.setAttribute('aria-current', 'location');
                        else section.link.removeAttribute('aria-current');
                    });

                    activeSection = next;
                    if (changed || !animate) moveIndicator(activeIndicator, next.link, true, animate, 8);
                    if (changed && hoveredLink === next.link) {
                        moveIndicator(hoverIndicator, next.link, false, true, 7);
                    }
                }

                function showHover(link) {
                    var section = null;
                    for (var i = 0; i < sections.length; i += 1) {
                        if (sections[i].link === link) {
                            section = sections[i];
                            break;
                        }
                    }
                    if (!section || !desktopQuery.matches || hoveredLink === link) return;

                    hoveredLink = link;
                    moveIndicator(hoverIndicator, link, section !== activeSection, true, 7);
                }

                function restoreHover() {
                    hoveredLink = null;
                    if (activeSection) moveIndicator(hoverIndicator, activeSection.link, false, true, 7);
                    else if (indicatorGsap) indicatorGsap.to(hoverIndicator, { autoAlpha: 0, duration: 0.26, ease: 'power2.out' });
                }

                function sectionAtReadingLine(candidates) {
                    var line = window.innerHeight * 0.35;
                    var nearest = null;
                    var nearestDistance = Infinity;

                    candidates.forEach(function (section) {
                        var rect = section.node.getBoundingClientRect();
                        var distance = line < rect.top ? rect.top - line : (line > rect.bottom ? line - rect.bottom : 0);
                        if (distance < nearestDistance) {
                            nearest = section;
                            nearestDistance = distance;
                        }
                    });
                    return nearest;
                }

                function syncFromViewport(animate) {
                    var section = sectionAtReadingLine(sections);
                    if (section) setActiveSection(section.id, animate);
                }

                function clearPending() {
                    pendingSectionId = null;
                    if (pendingTimer) window.clearTimeout(pendingTimer);
                    pendingTimer = null;
                }

                function onSectionClick(event) {
                    var link = event.target.closest ? event.target.closest('a[data-nav-section]') : null;
                    if (!link || !navList.contains(link)) return;

                    var id = link.getAttribute('data-nav-section');
                    var target = document.getElementById(id);
                    var url;
                    try { url = new URL(link.href, window.location.href); } catch (error) { return; }
                    if (!target || url.pathname !== window.location.pathname || url.search !== window.location.search) return;

                    pendingSectionId = id;
                    setActiveSection(id, true);
                    if (pendingTimer) window.clearTimeout(pendingTimer);
                    pendingTimer = window.setTimeout(function () {
                        clearPending();
                        syncFromViewport(true);
                    }, 2600);
                }

                function onPointerOver(event) {
                    var link = event.target.closest ? event.target.closest('a[data-nav-section]') : null;
                    if (link && navList.contains(link) && motion.fine()) showHover(link);
                    else if (hoveredLink) restoreHover();
                }

                function onFocusIn(event) {
                    var link = event.target.closest ? event.target.closest('a[data-nav-section]') : null;
                    if (link && navList.contains(link)) showHover(link);
                }

                function onFocusOut(event) {
                    var next = event.relatedTarget && event.relatedTarget.closest
                        ? event.relatedTarget.closest('a[data-nav-section]') : null;
                    if (next && navList.contains(next)) showHover(next);
                    else restoreHover();
                }

                function onResize() {
                    if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
                    resizeFrame = window.requestAnimationFrame(function () {
                        resizeFrame = 0;
                        observeSections();
                        syncFromViewport(false);
                        if (hoveredLink) {
                            for (var i = 0; i < sections.length; i += 1) {
                                if (sections[i].link === hoveredLink) {
                                    moveIndicator(hoverIndicator, hoveredLink, sections[i] !== activeSection, false, 7);
                                    break;
                                }
                            }
                        }
                    });
                }

                function onSectionsIntersect(entries) {
                    entries.forEach(function (entry) {
                        for (var i = 0; i < sections.length; i += 1) {
                            if (sections[i].node === entry.target) {
                                sections[i].intersecting = entry.isIntersecting;
                                break;
                            }
                        }
                    });

                    var intersecting = sections.filter(function (section) { return section.intersecting; });
                    if (!intersecting.length) return;

                    var current = sectionAtReadingLine(intersecting);
                    if (pendingSectionId && current.id !== pendingSectionId) return;
                    if (pendingSectionId === current.id) clearPending();
                    setActiveSection(current.id, true);
                }

                function observeSections() {
                    if (sectionObserver) sectionObserver.disconnect();
                    sections.forEach(function (section) { section.intersecting = false; });
                    var topMargin = Math.round(window.innerHeight * 0.28);
                    var bottomMargin = Math.round(window.innerHeight * 0.58);
                    sectionObserver = new IntersectionObserver(onSectionsIntersect, {
                        rootMargin: '-' + topMargin + 'px 0px -' + bottomMargin + 'px 0px',
                        threshold: 0
                    });
                    sections.forEach(function (section) { sectionObserver.observe(section.node); });
                }

                observeSections();
                navList.addEventListener('click', onSectionClick);
                navList.addEventListener('pointerover', onPointerOver);
                navList.addEventListener('pointerleave', restoreHover);
                navList.addEventListener('focusin', onFocusIn);
                navList.addEventListener('focusout', onFocusOut);
                window.addEventListener('resize', onResize, { passive: true });

                var initialSection = sectionAtReadingLine(sections);
                setActiveSection(initialSection ? initialSection.id : sections[0].id, window.pageYOffset > 16);

                motion.onCleanup(function () {
                    sectionObserver.disconnect();
                    navList.removeEventListener('click', onSectionClick);
                    navList.removeEventListener('pointerover', onPointerOver);
                    navList.removeEventListener('pointerleave', restoreHover);
                    navList.removeEventListener('focusin', onFocusIn);
                    navList.removeEventListener('focusout', onFocusOut);
                    window.removeEventListener('resize', onResize);
                    if (pendingTimer) window.clearTimeout(pendingTimer);
                    if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
                    if (indicatorGsap) indicatorGsap.killTweensOf([activeIndicator, hoverIndicator]);
                    if (indicatorHost.parentNode) indicatorHost.parentNode.removeChild(indicatorHost);
                });
            }
        }

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
