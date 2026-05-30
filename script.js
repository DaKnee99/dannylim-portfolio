// Clear grey placeholder background once image has loaded
document.querySelectorAll('.img-wrap img').forEach(img => {
  const clear = () => img.parentElement.style.background = 'transparent';
  if (img.complete && img.naturalWidth > 0) clear();
  else img.addEventListener('load', clear);
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', (e) => {
    const target = document.querySelector(anchor.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});
