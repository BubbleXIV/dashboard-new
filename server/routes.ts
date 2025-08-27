import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import passport from "passport";
import { Strategy as DiscordStrategy } from "passport-discord";
import session from "express-session";
import { insertUserSchema, insertGuildSchema, insertAttendanceEventSchema, insertFormSchema, insertGiveawaySchema, insertTwitchStreamerSchema } from "@shared/schema";

// Discord OAuth2 setup
passport.use(new DiscordStrategy({
  clientID: process.env.DISCORD_CLIENT_ID || '',
  clientSecret: process.env.DISCORD_CLIENT_SECRET || '',
  callbackURL: process.env.DISCORD_CALLBACK_URL || '/api/auth/discord/callback',
  scope: ['identify', 'guilds']
}, async (accessToken: string, refreshToken: string, profile: any, done: any) => {
  try {
    let user = await storage.getUserByDiscordId(profile.id);
    
    if (!user) {
      user = await storage.createUser({
        discordId: profile.id,
        username: profile.username,
        discriminator: profile.discriminator,
        avatar: profile.avatar,
        accessToken,
        refreshToken,
        tokenExpires: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000) // 7 days
      });
    } else {
      user = await storage.updateUser(user.id, {
        username: profile.username,
        discriminator: profile.discriminator,
        avatar: profile.avatar,
        accessToken,
        refreshToken,
        tokenExpires: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
      });
    }
    
    return done(null, user);
  } catch (error) {
    return done(error, null);
  }
}));

passport.serializeUser((user: any, done) => {
  done(null, user.id);
});

passport.deserializeUser(async (id: string, done) => {
  try {
    const user = await storage.getUser(id);
    done(null, user);
  } catch (error) {
    done(error, null);
  }
});

export async function registerRoutes(app: Express): Promise<Server> {
  // Session middleware
  app.use(session({
    secret: process.env.SESSION_SECRET || 'discord-bot-dashboard-secret',
    resave: false,
    saveUninitialized: false,
    cookie: { maxAge: 7 * 24 * 60 * 60 * 1000 } // 7 days
  }));

  app.use(passport.initialize());
  app.use(passport.session());

  // Auth middleware
  const requireAuth = (req: any, res: any, next: any) => {
    if (req.isAuthenticated()) {
      return next();
    }
    res.status(401).json({ message: 'Authentication required' });
  };

  // Discord OAuth routes
  app.get('/api/auth/discord', passport.authenticate('discord'));
  
  app.get('/api/auth/discord/callback', 
    passport.authenticate('discord', { failureRedirect: '/login' }),
    (req, res) => {
      res.redirect('/server-selection');
    }
  );

  app.post('/api/auth/logout', (req, res) => {
    req.logout((err) => {
      if (err) {
        return res.status(500).json({ message: 'Logout failed' });
      }
      res.json({ message: 'Logged out successfully' });
    });
  });

  app.get('/api/auth/user', (req, res) => {
    if (req.isAuthenticated()) {
      res.json(req.user);
    } else {
      res.status(401).json({ message: 'Not authenticated' });
    }
  });

  // Guild routes
  app.get('/api/guilds', requireAuth, async (req, res) => {
    try {
      const user = req.user as any;
      
      // Fetch user's Discord guilds
      const response = await fetch('https://discord.com/api/users/@me/guilds', {
        headers: {
          'Authorization': `Bearer ${user.accessToken}`
        }
      });
      
      if (!response.ok) {
        throw new Error('Failed to fetch Discord guilds');
      }
      
      const discordGuilds = await response.json();
      
      // Filter guilds where user has administrator permissions
      const adminGuilds = discordGuilds.filter((guild: any) => 
        (guild.permissions & 0x8) === 0x8 || guild.owner
      );
      
      // Store/update guild information
      const guilds = [];
      for (const discordGuild of adminGuilds) {
        let guild = await storage.getGuildByDiscordId(discordGuild.id);
        
        if (!guild) {
          guild = await storage.createGuild({
            discordId: discordGuild.id,
            name: discordGuild.name,
            icon: discordGuild.icon,
            ownerDiscordId: discordGuild.owner ? user.discordId : '',
            memberCount: discordGuild.approximate_member_count || 0,
            botJoined: false
          });
        } else {
          guild = await storage.updateGuild(guild.id, {
            name: discordGuild.name,
            icon: discordGuild.icon,
            memberCount: discordGuild.approximate_member_count || guild.memberCount
          });
        }
        
        if (guild) guilds.push(guild);
      }
      
      res.json(guilds);
    } catch (error) {
      console.error('Error fetching guilds:', error);
      res.status(500).json({ message: 'Failed to fetch guilds' });
    }
  });

  app.get('/api/guilds/:id', requireAuth, async (req, res) => {
    try {
      const guild = await storage.getGuild(req.params.id);
      if (!guild) {
        return res.status(404).json({ message: 'Guild not found' });
      }
      res.json(guild);
    } catch (error) {
      res.status(500).json({ message: 'Failed to fetch guild' });
    }
  });

  app.patch('/api/guilds/:id', requireAuth, async (req, res) => {
    try {
      const updateData = req.body;
      const guild = await storage.updateGuild(req.params.id, updateData);
      if (!guild) {
        return res.status(404).json({ message: 'Guild not found' });
      }
      res.json(guild);
    } catch (error) {
      res.status(500).json({ message: 'Failed to update guild' });
    }
  });

  // Attendance routes
  app.get('/api/guilds/:guildId/attendance', requireAuth, async (req, res) => {
    try {
      const events = await storage.getGuildAttendanceEvents(req.params.guildId);
      res.json(events);
    } catch (error) {
      res.status(500).json({ message: 'Failed to fetch attendance events' });
    }
  });

  app.post('/api/guilds/:guildId/attendance', requireAuth, async (req, res) => {
    try {
      const validatedData = insertAttendanceEventSchema.parse({
        ...req.body,
        guildId: req.params.guildId
      });
      
      const event = await storage.createAttendanceEvent(validatedData);
      res.json(event);
    } catch (error) {
      res.status(400).json({ message: 'Invalid attendance event data' });
    }
  });

  app.patch('/api/attendance/:id', requireAuth, async (req, res) => {
    try {
      const event = await storage.updateAttendanceEvent(req.params.id, req.body);
      if (!event) {
        return res.status(404).json({ message: 'Attendance event not found' });
      }
      res.json(event);
    } catch (error) {
      res.status(500).json({ message: 'Failed to update attendance event' });
    }
  });

  app.delete('/api/attendance/:id', requireAuth, async (req, res) => {
    try {
      const deleted = await storage.deleteAttendanceEvent(req.params.id);
      if (!deleted) {
        return res.status(404).json({ message: 'Attendance event not found' });
      }
      res.json({ message: 'Attendance event deleted' });
    } catch (error) {
      res.status(500).json({ message: 'Failed to delete attendance event' });
    }
  });

  // Form routes
  app.get('/api/guilds/:guildId/forms', requireAuth, async (req, res) => {
    try {
      const forms = await storage.getGuildForms(req.params.guildId);
      res.json(forms);
    } catch (error) {
      res.status(500).json({ message: 'Failed to fetch forms' });
    }
  });

  app.post('/api/guilds/:guildId/forms', requireAuth, async (req, res) => {
    try {
      const validatedData = insertFormSchema.parse({
        ...req.body,
        guildId: req.params.guildId
      });
      
      const form = await storage.createForm(validatedData);
      res.json(form);
    } catch (error) {
      res.status(400).json({ message: 'Invalid form data' });
    }
  });

  app.patch('/api/forms/:id', requireAuth, async (req, res) => {
    try {
      const form = await storage.updateForm(req.params.id, req.body);
      if (!form) {
        return res.status(404).json({ message: 'Form not found' });
      }
      res.json(form);
    } catch (error) {
      res.status(500).json({ message: 'Failed to update form' });
    }
  });

  app.delete('/api/forms/:id', requireAuth, async (req, res) => {
    try {
      const deleted = await storage.deleteForm(req.params.id);
      if (!deleted) {
        return res.status(404).json({ message: 'Form not found' });
      }
      res.json({ message: 'Form deleted' });
    } catch (error) {
      res.status(500).json({ message: 'Failed to delete form' });
    }
  });

  // Giveaway routes
  app.get('/api/guilds/:guildId/giveaways', requireAuth, async (req, res) => {
    try {
      const giveaways = await storage.getGuildGiveaways(req.params.guildId);
      res.json(giveaways);
    } catch (error) {
      res.status(500).json({ message: 'Failed to fetch giveaways' });
    }
  });

  app.post('/api/guilds/:guildId/giveaways', requireAuth, async (req, res) => {
    try {
      const validatedData = insertGiveawaySchema.parse({
        ...req.body,
        guildId: req.params.guildId
      });
      
      const giveaway = await storage.createGiveaway(validatedData);
      res.json(giveaway);
    } catch (error) {
      res.status(400).json({ message: 'Invalid giveaway data' });
    }
  });

  app.patch('/api/giveaways/:id', requireAuth, async (req, res) => {
    try {
      const giveaway = await storage.updateGiveaway(req.params.id, req.body);
      if (!giveaway) {
        return res.status(404).json({ message: 'Giveaway not found' });
      }
      res.json(giveaway);
    } catch (error) {
      res.status(500).json({ message: 'Failed to update giveaway' });
    }
  });

  app.delete('/api/giveaways/:id', requireAuth, async (req, res) => {
    try {
      const deleted = await storage.deleteGiveaway(req.params.id);
      if (!deleted) {
        return res.status(404).json({ message: 'Giveaway not found' });
      }
      res.json({ message: 'Giveaway deleted' });
    } catch (error) {
      res.status(500).json({ message: 'Failed to delete giveaway' });
    }
  });

  // Twitch routes
  app.get('/api/guilds/:guildId/twitch', requireAuth, async (req, res) => {
    try {
      const streamers = await storage.getGuildTwitchStreamers(req.params.guildId);
      res.json(streamers);
    } catch (error) {
      res.status(500).json({ message: 'Failed to fetch Twitch streamers' });
    }
  });

  app.post('/api/guilds/:guildId/twitch', requireAuth, async (req, res) => {
    try {
      const validatedData = insertTwitchStreamerSchema.parse({
        ...req.body,
        guildId: req.params.guildId
      });
      
      const streamer = await storage.createTwitchStreamer(validatedData);
      res.json(streamer);
    } catch (error) {
      res.status(400).json({ message: 'Invalid Twitch streamer data' });
    }
  });

  app.delete('/api/twitch/:id', requireAuth, async (req, res) => {
    try {
      const deleted = await storage.deleteTwitchStreamer(req.params.id);
      if (!deleted) {
        return res.status(404).json({ message: 'Twitch streamer not found' });
      }
      res.json({ message: 'Twitch streamer deleted' });
    } catch (error) {
      res.status(500).json({ message: 'Failed to delete Twitch streamer' });
    }
  });

  // Database file operations
  app.get('/api/database/:filename', requireAuth, async (req, res) => {
    try {
      const data = await storage.readDatabaseFile(req.params.filename);
      res.json(data);
    } catch (error) {
      res.status(500).json({ message: 'Failed to read database file' });
    }
  });

  app.post('/api/database/:filename', requireAuth, async (req, res) => {
    try {
      await storage.writeDatabaseFile(req.params.filename, req.body);
      res.json({ message: 'Database file updated' });
    } catch (error) {
      res.status(500).json({ message: 'Failed to write database file' });
    }
  });

  const httpServer = createServer(app);
  return httpServer;
}
