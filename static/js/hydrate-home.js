(function () {
  'use strict';

  var API = '/api/home';

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function injectProjects(projects) {
    var grid = document.querySelector('#work .work__grid');
    if (!grid || !Array.isArray(projects) || !projects.length) return;
    var html = projects.map(function (p) {
      var tags = (Array.isArray(p.tags) ? p.tags : []).map(function (t) {
        return '<span class="work__tag">' + esc(t) + '</span>';
      }).join('');
      var status = p.status_label
        ? '<span class="work__status work__status--' + esc(p.status) + '"><span class="sr-only">Project status: </span>' + esc(p.status_label) + '</span>'
        : '';
      var img = p.image
        ? '<img src="' + esc(p.image) + '" alt="' + esc(p.title) + '" class="work__image-img" loading="lazy">'
        : '<span class="work__image-icon"><i class="fa-solid fa-display"></i></span>';
      var actions = '';
      if (p.demo_url) {
        actions += '<a href="' + esc(p.demo_url) + '" target="_blank" rel="noopener noreferrer" class="work__link"><i class="fa-solid fa-arrow-up-right-from-square"></i> Live Demo</a>';
      }
      if (p.github) {
        actions += '<a href="' + esc(p.github) + '" target="_blank" rel="noopener noreferrer" class="work__link"><i class="fa-brands fa-github"></i> Source</a>';
      }
      return '<article class="work__card" data-category="' + esc(p.category || '') + '">' +
        '<div class="work__image" data-motion="image" data-parallax data-cursor="view">' +
          '<div class="work__image-placeholder">' + img + '</div>' +
        '</div>' +
        '<div class="work__info">' +
          status +
          '<h3 class="work__title">' + esc(p.title) + '</h3>' +
          '<p class="work__description">' + esc(p.description) + '</p>' +
          (tags ? '<div class="work__tags">' + tags + '</div>' : '') +
          (actions ? '<div class="work__actions">' + actions + '</div>' : '') +
        '</div>' +
      '</article>';
    }).join('');
    grid.innerHTML = html;
  }

  function injectTestimonials(testimonials) {
    var track = document.querySelector('#testimonials .testimonials__track');
    if (!track || !Array.isArray(testimonials) || !testimonials.length) return;
    var html = testimonials.map(function (t, i) {
      var role = String(t.role || '');
      var parts = role.split(',');
      var personRole = parts.length > 1 ? parts[0].trim() : '';
      var company = parts.length > 1 ? parts[1].trim() : role;
      var avatar = t.avatar_url
        ? '<img src="' + esc(t.avatar_url) + '" alt="' + esc(t.name) + '" loading="lazy">'
        : '<i class="fa-solid fa-user" aria-hidden="true"></i>';
      var authorExtra = '';
      if (personRole) authorExtra += '<span>' + esc(personRole) + '</span>';
      if (company) authorExtra += '<small>' + esc(company) + '</small>';
      return '<article class="testimonial-card" data-motion="reveal" data-motion-delay="' + (i * 100) + '">' +
        '<div class="testimonial-card__top">' +
          '<div class="testimonial-card__avatar">' + avatar + '</div>' +
          (company ? '<div class="testimonial-card__company">' + esc(company) + '</div>' : '') +
        '</div>' +
        '<div class="testimonial-card__quote">&ldquo;</div>' +
        '<p class="testimonial-card__text">' + esc(t.text) + '</p>' +
        '<div class="testimonial-card__author">' +
          '<strong>' + esc(t.name) + '</strong>' + authorExtra +
        '</div>' +
      '</article>';
    }).join('');
    track.innerHTML = html;
  }

  function injectBlog(posts) {
    var grid = document.querySelector('#blog .home-journal-preview__grid');
    if (!grid || !Array.isArray(posts) || !posts.length) return;
    var html = posts.map(function (post) {
      var slug = esc(post.slug);
      var href = '/blog/' + slug;
      var img = post.hero_image
        ? '<a href="' + href + '" class="journal-card__image" data-motion="image" data-cursor="view" aria-label="Read ' + esc(post.title) + '">' +
            '<img src="' + esc(post.hero_image) + '" alt="' + esc(post.title) + '" loading="lazy" ' +
            'onerror="this.parentNode.classList.add(\'journal-card__image--broken\');this.remove();">' +
          '</a>'
        : '';
      var meta = '<div class="journal-card__meta">' +
        '<span class="journal-card__type">' + esc(post.content_type_label || 'Insight') + '</span>' +
        (post.category ? '<span class="journal-card__cat">' + esc(post.category) + '</span>' : '') +
        (post.source_name ? '<span class="journal-card__src">via ' + esc(post.source_name) + '</span>' : '') +
      '</div>';
      var date = post.display_date
        ? '<time class="journal-card__date" datetime="' + esc(post.display_date) + '">' + esc(post.display_date_label || '') + '</time>'
        : '';
      var summary = post.summary
        ? '<p class="journal-card__summary">' + esc(post.summary) + '</p>'
        : '';
      return '<article class="journal-card journal-card--home-preview blog__card" data-motion="card">' +
        img +
        '<div class="journal-card__body">' +
          meta +
          date +
          '<h3><a href="' + href + '">' + esc(post.title) + '</a></h3>' +
          summary +
          '<a href="' + href + '" class="journal-card__link">Read article <i class="fa-solid fa-arrow-right" aria-hidden="true"></i></a>' +
        '</div>' +
      '</article>';
    }).join('');
    grid.innerHTML = html;
  }

  function hydrate() {
    fetch(API, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        injectProjects(d.projects);
        injectTestimonials(d.testimonials);
        injectBlog(d.blog_posts);
      })
      .catch(function () {});
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hydrate);
  } else {
    hydrate();
  }
})();
