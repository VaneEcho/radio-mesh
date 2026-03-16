import { createRouter, createWebHistory } from 'vue-router'
import StationsView      from '../views/StationsView.vue'
import SpectrumView      from '../views/SpectrumView.vue'
import BandRulesView     from '../views/BandRulesView.vue'
import FreqQueryView     from '../views/FreqQueryView.vue'
import FreqAssignView    from '../views/FreqAssignView.vue'
import TaskView          from '../views/TaskView.vue'
import RealtimeView      from '../views/RealtimeView.vue'
import PlaybackView      from '../views/PlaybackView.vue'
import AnalysisView      from '../views/AnalysisView.vue'
import SignalLibraryView from '../views/SignalLibraryView.vue'

const routes = [
  { path: '/',                    component: StationsView,      name: 'stations'        },
  { path: '/spectrum/:stationId', component: SpectrumView,      name: 'spectrum'        },
  { path: '/band-rules',          component: BandRulesView,     name: 'band-rules'      },
  { path: '/freq-query',          component: FreqQueryView,     name: 'freq-query'      },
  { path: '/freq-assign',         component: FreqAssignView,    name: 'freq-assign'     },
  { path: '/tasks',               component: TaskView,          name: 'tasks'           },
  { path: '/realtime',            component: RealtimeView,      name: 'realtime'        },
  { path: '/playback',            component: PlaybackView,      name: 'playback'        },
  { path: '/analysis',            component: AnalysisView,      name: 'analysis'        },
  { path: '/signals',             component: SignalLibraryView, name: 'signal-library'  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
