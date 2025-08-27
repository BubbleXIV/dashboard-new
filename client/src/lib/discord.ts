export function getDiscordAvatarUrl(discordId: string, avatar: string | null): string {
  if (!avatar) {
    // Default Discord avatar
    const defaultAvatar = (parseInt(discordId) % 5).toString();
    return `https://cdn.discordapp.com/embed/avatars/${defaultAvatar}.png`;
  }
  
  return `https://cdn.discordapp.com/avatars/${discordId}/${avatar}.png`;
}

export function getDiscordGuildIconUrl(guildId: string, icon: string | null): string {
  if (!icon) {
    return '';
  }
  
  return `https://cdn.discordapp.com/icons/${guildId}/${icon}.png`;
}

export function formatDiscordTimestamp(date: Date | string): string {
  const timestamp = Math.floor(new Date(date).getTime() / 1000);
  return `<t:${timestamp}:R>`;
}

export function parseDiscordPermissions(permissions: string): {
  administrator: boolean;
  manageGuild: boolean;
  manageRoles: boolean;
  manageChannels: boolean;
} {
  const perms = parseInt(permissions);
  
  return {
    administrator: (perms & 0x8) === 0x8,
    manageGuild: (perms & 0x20) === 0x20,
    manageRoles: (perms & 0x10000000) === 0x10000000,
    manageChannels: (perms & 0x10) === 0x10,
  };
}

export function formatMemberCount(count: number): string {
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  } else if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}k`;
  }
  return count.toString();
}
