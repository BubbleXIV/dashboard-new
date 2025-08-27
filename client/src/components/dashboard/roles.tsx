import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Plus, Edit, Trash2 } from "lucide-react";
import type { Guild } from "@shared/schema";

interface RolesProps {
  guild: Guild;
}

export default function Roles({ guild }: RolesProps) {
  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold mb-2 text-discord-text">Roles & Autoroles</h2>
        <p className="text-discord-text-secondary">Manage server roles and automatic role assignment</p>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Role Management */}
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
            <CardTitle className="text-lg font-semibold text-discord-text">Server Roles</CardTitle>
            <Button 
              className="bg-discord-blurple hover:bg-discord-dark-blurple"
              size="sm"
              data-testid="button-create-role"
            >
              <Plus className="h-4 w-4 mr-2" />
              Create Role
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-3 max-h-80 overflow-y-auto">
              {/* No roles state */}
              <div className="text-center py-8 text-discord-text-muted">
                <p>No custom roles configured</p>
                <p className="text-sm mt-1">Bot can only manage roles created through this dashboard</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        {/* Autoroles */}
        <Card className="bg-discord-secondary border-discord-tertiary">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
            <CardTitle className="text-lg font-semibold text-discord-text">Auto Roles</CardTitle>
            <Button 
              className="bg-discord-success hover:bg-green-600"
              size="sm"
              data-testid="button-add-auto-role"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Auto Role
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="p-4 bg-discord-tertiary rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-medium text-discord-text">New Member Role</h4>
                  <Switch 
                    defaultChecked={false}
                    data-testid="switch-new-member-role"
                  />
                </div>
                <p className="text-sm text-discord-text-secondary">
                  Automatically assign @Newcomer role to new members
                </p>
              </div>
              
              <div className="p-4 bg-discord-tertiary rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-medium text-discord-text">Reaction Role</h4>
                  <Switch 
                    defaultChecked={false}
                    data-testid="switch-reaction-role"
                  />
                </div>
                <p className="text-sm text-discord-text-secondary">
                  React with 🎮 to get @Gamer role
                </p>
              </div>
              
              {/* Empty state */}
              <div className="text-center py-4 text-discord-text-muted">
                <p className="text-sm">Configure auto roles to automatically assign roles to members</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
