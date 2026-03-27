import { BarChart2, Download, Upload } from 'lucide-react'

import type { PluginManifest } from '@core/types/plugin'

import StatsIndexPage  from './src/pages/stats/index'
import StatsGroupPage  from './src/pages/stats/group'
import StatsUserPage   from './src/pages/stats/user'
import ImportPage      from './src/pages/import/index'
import DlStatsPage     from '../../yoink-dl/frontend/src/pages/admin/stats/index'

export const statsPlugin: PluginManifest = {
  id: 'stats',
  name: 'Yoink Stats',

  routes: [
    { path: '/stats',                      element: <StatsIndexPage />, minRole: 'user' },
    { path: '/stats/import',               element: <ImportPage />,     minRole: 'owner' },
    { path: '/stats/:chatId',              element: <StatsGroupPage />, minRole: 'user' },
    { path: '/stats/:chatId/user/:userId', element: <StatsUserPage />,  minRole: 'user' },
    { path: '/admin/stats',                element: <DlStatsPage />,    minRole: 'admin' },
  ],

  navGroups: [
    {
      label: 'Stats',
      i18nKey: 'nav.stats',
      icon: <BarChart2 className="h-4 w-4" />,
      minRole: ['owner', 'admin', 'moderator', 'user'],
      items: [
        { label: 'Chat Stats',     i18nKey: 'nav.chat_stats',     path: '/stats',        icon: <BarChart2 className="h-4 w-4" />, minRole: ['owner', 'admin', 'moderator', 'user'] },
        { label: 'Download Stats', i18nKey: 'nav.admin_stats',    path: '/admin/stats',  icon: <Download  className="h-4 w-4" />, minRole: ['owner', 'admin'] },
        { label: 'Import History', i18nKey: 'nav.import_history', path: '/stats/import', icon: <Upload    className="h-4 w-4" />, minRole: ['owner'] },
      ],
    },
  ],

  resources: [
    { name: 'stats-groups', list: '/stats',        meta: { label: 'Stats' } },
    { name: 'stats-import', list: '/stats/import', meta: { label: 'Import History' } },
  ],
}
