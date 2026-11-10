import { S, peerId } from './state.js';
import { esc, initials, icon } from './util.js';

export function avatar(u, size = 'md', { ring = true } = {}) {
  u = u || { name: '?', color: '#999' };
  const inner = u.avatar ? `<img src="${esc(u.avatar)}" alt="" loading="lazy">` : `<span>${esc(initials(u.name))}</span>`;
  return `<span class="av av-${size} ${ring && u.online ? 'on' : ''}" style="--c:${esc(u.color || '#999')}">${inner}</span>`;
}
export function chatAvatar(c, size = 'md', opts) {
  if (c.type === 'self') return `<span class="av av-${size} av-self">${icon('sparkle')}</span>`;
  if (c.type === 'group') return `<span class="av av-${size} av-group" style="--c:${esc(c.color || '#3d7bfd')}"><span>${esc(initials(c.title))}</span></span>`;
  return avatar(S.users[peerId(c)], size, opts);
}
