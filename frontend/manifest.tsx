import { BarChart2 } from 'lucide-react'

import type { PluginManifest } from '@core/types/plugin'

import StatsIndexPage  from './src/pages/stats/index'
import StatsGroupPage  from './src/pages/stats/group'
import StatsUserPage   from './src/pages/stats/user'
import ImportPage      from './src/pages/import/index'

export const statsPlugin: PluginManifest = {
  id: 'stats',
  name: 'Yoink Stats',

  routes: [
    { path: '/stats',                      element: <StatsIndexPage />, minRole: 'user' },
    { path: '/stats/import',               element: <ImportPage />,     minRole: 'owner' },
    { path: '/stats/:chatId',              element: <StatsGroupPage />, minRole: 'user' },
    { path: '/stats/:chatId/user/:userId', element: <StatsUserPage />,  minRole: 'user' },
  ],

  navGroups: [
    {
      label: 'Stats',
      i18nKey: 'nav.stats',
      icon: <BarChart2 className="h-4 w-4" />,
      items: [
        { label: 'Chat Stats', i18nKey: 'nav.chat_stats', path: '/stats', icon: <BarChart2 className="h-4 w-4" />, minRole: ['owner', 'admin', 'moderator', 'user'] },
      ],
    },
  ],

  resources: [
    { name: 'stats-groups', list: '/stats', meta: { label: 'Stats' } },
  ],
}
