import { type User, type InsertUser, type Guild, type InsertGuild, 
         type AttendanceEvent, type InsertAttendanceEvent,
         type Form, type InsertForm, type Giveaway, type InsertGiveaway,
         type TwitchStreamer, type InsertTwitchStreamer } from "@shared/schema";
import { randomUUID } from "crypto";
import fs from "fs/promises";
import path from "path";

export interface IStorage {
  // User operations
  getUser(id: string): Promise<User | undefined>;
  getUserByDiscordId(discordId: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  updateUser(id: string, user: Partial<User>): Promise<User | undefined>;

  // Guild operations
  getGuild(id: string): Promise<Guild | undefined>;
  getGuildByDiscordId(discordId: string): Promise<Guild | undefined>;
  getUserGuilds(userId: string): Promise<Guild[]>;
  createGuild(guild: InsertGuild): Promise<Guild>;
  updateGuild(id: string, guild: Partial<Guild>): Promise<Guild | undefined>;

  // Attendance operations
  getGuildAttendanceEvents(guildId: string): Promise<AttendanceEvent[]>;
  getAttendanceEvent(id: string): Promise<AttendanceEvent | undefined>;
  createAttendanceEvent(event: InsertAttendanceEvent): Promise<AttendanceEvent>;
  updateAttendanceEvent(id: string, event: Partial<AttendanceEvent>): Promise<AttendanceEvent | undefined>;
  deleteAttendanceEvent(id: string): Promise<boolean>;

  // Form operations
  getGuildForms(guildId: string): Promise<Form[]>;
  getForm(id: string): Promise<Form | undefined>;
  createForm(form: InsertForm): Promise<Form>;
  updateForm(id: string, form: Partial<Form>): Promise<Form | undefined>;
  deleteForm(id: string): Promise<boolean>;

  // Giveaway operations
  getGuildGiveaways(guildId: string): Promise<Giveaway[]>;
  getGiveaway(id: string): Promise<Giveaway | undefined>;
  createGiveaway(giveaway: InsertGiveaway): Promise<Giveaway>;
  updateGiveaway(id: string, giveaway: Partial<Giveaway>): Promise<Giveaway | undefined>;
  deleteGiveaway(id: string): Promise<boolean>;

  // Twitch operations
  getGuildTwitchStreamers(guildId: string): Promise<TwitchStreamer[]>;
  getTwitchStreamer(id: string): Promise<TwitchStreamer | undefined>;
  createTwitchStreamer(streamer: InsertTwitchStreamer): Promise<TwitchStreamer>;
  updateTwitchStreamer(id: string, streamer: Partial<TwitchStreamer>): Promise<TwitchStreamer | undefined>;
  deleteTwitchStreamer(id: string): Promise<boolean>;

  // Database file operations
  readDatabaseFile(filename: string): Promise<any>;
  writeDatabaseFile(filename: string, data: any): Promise<void>;
}

export class MemStorage implements IStorage {
  private users: Map<string, User>;
  private guilds: Map<string, Guild>;
  private userGuilds: Map<string, string[]>; // userId -> guildIds
  private attendanceEvents: Map<string, AttendanceEvent>;
  private forms: Map<string, Form>;
  private giveaways: Map<string, Giveaway>;
  private twitchStreamers: Map<string, TwitchStreamer>;
  private databasePath: string;

  constructor() {
    this.users = new Map();
    this.guilds = new Map();
    this.userGuilds = new Map();
    this.attendanceEvents = new Map();
    this.forms = new Map();
    this.giveaways = new Map();
    this.twitchStreamers = new Map();
    this.databasePath = path.join(process.cwd(), 'databases');
    this.ensureDatabaseDirectory();
  }

  private async ensureDatabaseDirectory() {
    try {
      await fs.mkdir(this.databasePath, { recursive: true });
    } catch (error) {
      console.error('Failed to create databases directory:', error);
    }
  }

  // User operations
  async getUser(id: string): Promise<User | undefined> {
    return this.users.get(id);
  }

  async getUserByDiscordId(discordId: string): Promise<User | undefined> {
    return Array.from(this.users.values()).find(user => user.discordId === discordId);
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const id = randomUUID();
    const user: User = { 
      ...insertUser, 
      id, 
      createdAt: new Date(),
      discriminator: insertUser.discriminator || null,
      avatar: insertUser.avatar || null,
      accessToken: insertUser.accessToken || null,
      refreshToken: insertUser.refreshToken || null,
      tokenExpires: insertUser.tokenExpires || null,
    };
    this.users.set(id, user);
    return user;
  }

  async updateUser(id: string, updates: Partial<User>): Promise<User | undefined> {
    const user = this.users.get(id);
    if (!user) return undefined;
    
    const updatedUser = { ...user, ...updates };
    this.users.set(id, updatedUser);
    return updatedUser;
  }

  // Guild operations
  async getGuild(id: string): Promise<Guild | undefined> {
    return this.guilds.get(id);
  }

  async getGuildByDiscordId(discordId: string): Promise<Guild | undefined> {
    return Array.from(this.guilds.values()).find(guild => guild.discordId === discordId);
  }

  async getUserGuilds(userId: string): Promise<Guild[]> {
    const guildIds = this.userGuilds.get(userId) || [];
    return guildIds.map(id => this.guilds.get(id)).filter(Boolean) as Guild[];
  }

  async createGuild(insertGuild: InsertGuild): Promise<Guild> {
    const id = randomUUID();
    const guild: Guild = { 
      ...insertGuild, 
      id, 
      createdAt: new Date(),
      icon: insertGuild.icon || null,
      settings: insertGuild.settings || {},
    };
    this.guilds.set(id, guild);
    return guild;
  }

  async updateGuild(id: string, updates: Partial<Guild>): Promise<Guild | undefined> {
    const guild = this.guilds.get(id);
    if (!guild) return undefined;
    
    const updatedGuild = { ...guild, ...updates };
    this.guilds.set(id, updatedGuild);
    return updatedGuild;
  }

  // Attendance operations
  async getGuildAttendanceEvents(guildId: string): Promise<AttendanceEvent[]> {
    return Array.from(this.attendanceEvents.values())
      .filter(event => event.guildId === guildId)
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }

  async getAttendanceEvent(id: string): Promise<AttendanceEvent | undefined> {
    return this.attendanceEvents.get(id);
  }

  async createAttendanceEvent(insertEvent: InsertAttendanceEvent): Promise<AttendanceEvent> {
    const id = randomUUID();
    const event: AttendanceEvent = { 
      ...insertEvent, 
      id, 
      createdAt: new Date(),
      description: insertEvent.description || null,
      channelId: insertEvent.channelId || null,
      messageId: insertEvent.messageId || null,
    };
    this.attendanceEvents.set(id, event);
    return event;
  }

  async updateAttendanceEvent(id: string, updates: Partial<AttendanceEvent>): Promise<AttendanceEvent | undefined> {
    const event = this.attendanceEvents.get(id);
    if (!event) return undefined;
    
    const updatedEvent = { ...event, ...updates };
    this.attendanceEvents.set(id, updatedEvent);
    return updatedEvent;
  }

  async deleteAttendanceEvent(id: string): Promise<boolean> {
    return this.attendanceEvents.delete(id);
  }

  // Form operations
  async getGuildForms(guildId: string): Promise<Form[]> {
    return Array.from(this.forms.values())
      .filter(form => form.guildId === guildId)
      .sort((a, b) => new Date(b.createdAt!).getTime() - new Date(a.createdAt!).getTime());
  }

  async getForm(id: string): Promise<Form | undefined> {
    return this.forms.get(id);
  }

  async createForm(insertForm: InsertForm): Promise<Form> {
    const id = randomUUID();
    const form: Form = { 
      ...insertForm, 
      id, 
      createdAt: new Date(),
      description: insertForm.description || null,
    };
    this.forms.set(id, form);
    return form;
  }

  async updateForm(id: string, updates: Partial<Form>): Promise<Form | undefined> {
    const form = this.forms.get(id);
    if (!form) return undefined;
    
    const updatedForm = { ...form, ...updates };
    this.forms.set(id, updatedForm);
    return updatedForm;
  }

  async deleteForm(id: string): Promise<boolean> {
    return this.forms.delete(id);
  }

  // Giveaway operations
  async getGuildGiveaways(guildId: string): Promise<Giveaway[]> {
    return Array.from(this.giveaways.values())
      .filter(giveaway => giveaway.guildId === guildId)
      .sort((a, b) => new Date(b.createdAt!).getTime() - new Date(a.createdAt!).getTime());
  }

  async getGiveaway(id: string): Promise<Giveaway | undefined> {
    return this.giveaways.get(id);
  }

  async createGiveaway(insertGiveaway: InsertGiveaway): Promise<Giveaway> {
    const id = randomUUID();
    const giveaway: Giveaway = { 
      ...insertGiveaway, 
      id, 
      createdAt: new Date(),
      description: insertGiveaway.description || null,
      channelId: insertGiveaway.channelId || null,
      messageId: insertGiveaway.messageId || null,
    };
    this.giveaways.set(id, giveaway);
    return giveaway;
  }

  async updateGiveaway(id: string, updates: Partial<Giveaway>): Promise<Giveaway | undefined> {
    const giveaway = this.giveaways.get(id);
    if (!giveaway) return undefined;
    
    const updatedGiveaway = { ...giveaway, ...updates };
    this.giveaways.set(id, updatedGiveaway);
    return updatedGiveaway;
  }

  async deleteGiveaway(id: string): Promise<boolean> {
    return this.giveaways.delete(id);
  }

  // Twitch operations
  async getGuildTwitchStreamers(guildId: string): Promise<TwitchStreamer[]> {
    return Array.from(this.twitchStreamers.values())
      .filter(streamer => streamer.guildId === guildId)
      .sort((a, b) => a.username.localeCompare(b.username));
  }

  async getTwitchStreamer(id: string): Promise<TwitchStreamer | undefined> {
    return this.twitchStreamers.get(id);
  }

  async createTwitchStreamer(insertStreamer: InsertTwitchStreamer): Promise<TwitchStreamer> {
    const id = randomUUID();
    const streamer: TwitchStreamer = { 
      ...insertStreamer, 
      id, 
      createdAt: new Date(),
      gameName: insertStreamer.gameName || null,
      streamTitle: insertStreamer.streamTitle || null,
      lastChecked: insertStreamer.lastChecked || null,
      notificationChannelId: insertStreamer.notificationChannelId || null,
    };
    this.twitchStreamers.set(id, streamer);
    return streamer;
  }

  async updateTwitchStreamer(id: string, updates: Partial<TwitchStreamer>): Promise<TwitchStreamer | undefined> {
    const streamer = this.twitchStreamers.get(id);
    if (!streamer) return undefined;
    
    const updatedStreamer = { ...streamer, ...updates };
    this.twitchStreamers.set(id, updatedStreamer);
    return updatedStreamer;
  }

  async deleteTwitchStreamer(id: string): Promise<boolean> {
    return this.twitchStreamers.delete(id);
  }

  // Database file operations
  async readDatabaseFile(filename: string): Promise<any> {
    try {
      const filePath = path.join(this.databasePath, filename);
      const data = await fs.readFile(filePath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      if ((error as any).code === 'ENOENT') {
        return {}; // File doesn't exist, return empty object
      }
      throw error;
    }
  }

  async writeDatabaseFile(filename: string, data: any): Promise<void> {
    try {
      const filePath = path.join(this.databasePath, filename);
      await fs.writeFile(filePath, JSON.stringify(data, null, 2));
    } catch (error) {
      console.error(`Failed to write database file ${filename}:`, error);
      throw error;
    }
  }
}

export const storage = new MemStorage();
