(function(){
  const root = document.documentElement;
  const toggle = document.getElementById('theme-toggle');
  const stored = localStorage.getItem('tk_theme') || 'light';
  function applyTheme(t){
    root.setAttribute('data-theme', t);
    if(toggle){
      toggle.innerHTML = t === 'dark' ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
      toggle.setAttribute('aria-pressed', t==='dark');
    }
  }
  applyTheme(stored);
  if(toggle){
    toggle.addEventListener('click', ()=>{
      const next = (root.getAttribute('data-theme') === 'dark') ? 'light' : 'dark';
      localStorage.setItem('tk_theme', next);
      applyTheme(next);
    });
  }
  // Move server-rendered alerts into the toast container and auto-dismiss
  function initToasts(){
    const container = document.getElementById('toast-container');
    if(!container) return;
    const alerts = Array.from(document.querySelectorAll('main .alert.toast-item'));
    alerts.forEach(a => {
      container.appendChild(a);
      const persist = a.classList.contains('warning') || a.classList.contains('danger');
      setTimeout(()=>{ try{ a.classList.remove('show'); a.remove(); }catch(e){} }, persist ? 7000 : 4500);
    });
  }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initToasts);
  else initToasts();
})();
