import { sql } from "drizzle-orm";
import { pgTable, text, varchar, timestamp, integer, boolean, jsonb } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const users = pgTable("users", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  discordId: text("discord_id").notNull().unique(),
  username: text("username").notNull(),
  discriminator: text("discriminator"),
  avatar: text("avatar"),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  tokenExpires: timestamp("token_expires"),
  createdAt: timestamp("created_at").defaultNow(),
});

export const guilds = pgTable("guilds", {
  id: varchar("id").primaryKey(),
  discordId: text("discord_id").notNull().unique(),
  name: text("name").notNull(),
  icon: text("icon"),
  ownerDiscordId: text("owner_discord_id").notNull(),
  memberCount: integer("member_count").default(0),
  botJoined: boolean("bot_joined").default(false),
  settings: jsonb("settings").$type<{
    prefix?: string;
    autoDelete?: boolean;
    dmResponses?: boolean;
    logChannel?: string;
    logging?: {
      memberEvents?: boolean;
      messageEvents?: boolean;
      roleEvents?: boolean;
    };
  }>().default({}),
  createdAt: timestamp("created_at").defaultNow(),
});

export const userGuilds = pgTable("user_guilds", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  userId: varchar("user_id").notNull().references(() => users.id),
  guildId: varchar("guild_id").notNull().references(() => guilds.id),
  permissions: text("permissions").notNull(),
  isAdmin: boolean("is_admin").default(false),
  isOwner: boolean("is_owner").default(false),
});

export const attendanceEvents = pgTable("attendance_events", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  guildId: varchar("guild_id").notNull().references(() => guilds.id),
  name: text("name").notNull(),
  description: text("description"),
  date: timestamp("date").notNull(),
  isRecurring: boolean("is_recurring").default(false),
  roles: jsonb("roles").$type<Array<{
    name: string;
    required: number;
    current: number;
  }>>().default([]),
  attendees: jsonb("attendees").$type<Array<{
    userId: string;
    username: string;
    role?: string;
  }>>().default([]),
  channelId: text("channel_id"),
  messageId: text("message_id"),
  createdAt: timestamp("created_at").defaultNow(),
});

export const forms = pgTable("forms", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  guildId: varchar("guild_id").notNull().references(() => guilds.id),
  name: text("name").notNull(),
  description: text("description"),
  questions: jsonb("questions").$type<Array<{
    id: string;
    type: 'text' | 'textarea' | 'select' | 'multiselect';
    question: string;
    required: boolean;
    options?: string[];
  }>>().default([]),
  responses: jsonb("responses").$type<Array<{
    userId: string;
    username: string;
    answers: Record<string, string | string[]>;
    submittedAt: string;
  }>>().default([]),
  isActive: boolean("is_active").default(true),
  createdAt: timestamp("created_at").defaultNow(),
});

export const giveaways = pgTable("giveaways", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  guildId: varchar("guild_id").notNull().references(() => guilds.id),
  title: text("title").notNull(),
  description: text("description"),
  prize: text("prize").notNull(),
  winnerCount: integer("winner_count").default(1),
  endsAt: timestamp("ends_at").notNull(),
  entries: jsonb("entries").$type<Array<{
    userId: string;
    username: string;
  }>>().default([]),
  winners: jsonb("winners").$type<Array<{
    userId: string;
    username: string;
  }>>().default([]),
  channelId: text("channel_id"),
  messageId: text("message_id"),
  isActive: boolean("is_active").default(true),
  createdAt: timestamp("created_at").defaultNow(),
});

export const twitchStreamers = pgTable("twitch_streamers", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  guildId: varchar("guild_id").notNull().references(() => guilds.id),
  username: text("username").notNull(),
  isLive: boolean("is_live").default(false),
  viewerCount: integer("viewer_count").default(0),
  gameName: text("game_name"),
  streamTitle: text("stream_title"),
  lastChecked: timestamp("last_checked"),
  notificationChannelId: text("notification_channel_id"),
  createdAt: timestamp("created_at").defaultNow(),
});

// Insert schemas
export const insertUserSchema = createInsertSchema(users).omit({
  id: true,
  createdAt: true,
});

export const insertGuildSchema = createInsertSchema(guilds).omit({
  createdAt: true,
});

export const insertAttendanceEventSchema = createInsertSchema(attendanceEvents).omit({
  id: true,
  createdAt: true,
});

export const insertFormSchema = createInsertSchema(forms).omit({
  id: true,
  createdAt: true,
});

export const insertGiveawaySchema = createInsertSchema(giveaways).omit({
  id: true,
  createdAt: true,
});

export const insertTwitchStreamerSchema = createInsertSchema(twitchStreamers).omit({
  id: true,
  createdAt: true,
  lastChecked: true,
});

// Types
export type User = typeof users.$inferSelect;
export type InsertUser = z.infer<typeof insertUserSchema>;
export type Guild = typeof guilds.$inferSelect;
export type InsertGuild = z.infer<typeof insertGuildSchema>;
export type AttendanceEvent = typeof attendanceEvents.$inferSelect;
export type InsertAttendanceEvent = z.infer<typeof insertAttendanceEventSchema>;
export type Form = typeof forms.$inferSelect;
export type InsertForm = z.infer<typeof insertFormSchema>;
export type Giveaway = typeof giveaways.$inferSelect;
export type InsertGiveaway = z.infer<typeof insertGiveawaySchema>;
export type TwitchStreamer = typeof twitchStreamers.$inferSelect;
export type InsertTwitchStreamer = z.infer<typeof insertTwitchStreamerSchema>;
