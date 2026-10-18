(function() {
  const API = '/api/home';
  function injectProjects(data) {
    const container = document.querySelector('#work');
    if (!container || !Array.isArray(data.projects)) return;
    const cards = container.querySelectorAll('.work__grid .work__card');
    data.projects.slice(0, cards.length).forEach((p, i) => {
      const card = cards[i];
      if (!card) return;
      const title = card.querySelector('.work__title');
      const desc = card.querySelector('.work__desc');
      const github = card.querySelector('a[href*="github"]');
      const demo = card.querySelector('a[href*="demo"], a[target="_blank"]:not([href*="github"])');
      if (title) title.textContent = p.title || title.textContent;
      if (desc) desc.textContent = p.description || desc.textContent;
      if (github && p.github) github.href = p.github;
      if (demo && p.demo_url) demo.href = p.demo_url;
    });
  }
  function injectTestimonials(data) {
    const wrap = document.querySelector('.testimonials__list');
    if (!wrap) return;
  }
  function injectBlog(data) {
    const wrap = document.querySelector('.journal__grid, #journal .journal__grid');
    if (!wrap || !Array.isArray(data.blog_posts)) return;
  }
  function injectFunFacts(data) {
    if (!Array.isArray(data.fun_facts)) return;
  }
  fetch(API).then(r => r.ok ? r.json() : null).then(d => {
    if (!d) return;
    injectProjects(d);
    injectTestimonials(d);
    injectBlog(d);
    injectFunFacts(d);
  }).catch(()=>{});
})();
(function() {
  const API = '/api/home';
  function hydrate() {
    fetch(API, {cache: 'no-store'}).then(r => r.ok ? r.json() : null).then(d => {
      if (!d) return;
      const workGrid = document.querySelector('#work .work__grid');
      if (workGrid && Array.isArray(d.projects)) {
        const cards = workGrid.querySelectorAll('.work__card');
        d.projects.slice(0, cards.length).forEach((p,i)=>{
          const c = cards[i]; if(!c) return;
          const t=c.querySelector('.work__title'); if(t) t.textContent=p.title||t.textContent;
          const desc=c.querySelector('.work__desc'); if(desc) desc.textContent=p.description||desc.textContent;
          const gh=c.querySelector('a[href*="github"]'); if(gh&&p.github) gh.href=p.github;
          const demo=c.querySelectorAll('a[target="_blank"]'); demo.forEach(a=>{
            if(a.href.includes('github')) return;
            if(p.demo_url) a.href=p.demo_url;
          });
        });
      }
    }).catch(()=>{});
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded', hydrate);
  else hydrate();
})();
