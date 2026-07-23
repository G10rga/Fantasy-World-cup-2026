/** Shared player avatar HTML (photo → flag → initials). */
function playerAvatarHtml(player, sizeClass = 'w-10 h-10') {
  const name = player?.name || '?';
  const photo = player?.photo_url || '';
  const flag = player?.country?.flag_url || '';
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase() || '?';

  const fallback = flag
    ? `<img alt="" class="w-full h-full object-cover opacity-80" src="${flag}" onerror="this.remove()">`
    : `<span class="text-[10px] font-stat-md text-on-surface-variant">${initials}</span>`;

  if (photo) {
    return `
      <div class="${sizeClass} rounded-full bg-surface-variant border border-outline overflow-hidden flex-shrink-0 flex items-center justify-center relative">
        <img alt="" class="w-full h-full object-cover absolute inset-0" src="${photo}"
             onerror="this.style.display='none'; this.parentElement.querySelector('[data-avatar-fallback]')?.classList.remove('hidden')">
        <div data-avatar-fallback class="hidden w-full h-full flex items-center justify-center">${fallback}</div>
      </div>`;
  }

  return `
    <div class="${sizeClass} rounded-full bg-surface-variant border border-outline overflow-hidden flex-shrink-0 flex items-center justify-center">
      ${fallback}
    </div>`;
}
