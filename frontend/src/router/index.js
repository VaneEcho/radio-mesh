import { createRouter, createWebHistory } from 'vue-router'
import StationsView   from '../views/StationsView.vue'
import SpectrumView   from '../views/SpectrumView.vue'
import BandRulesView  from '../views/BandRulesView.vue'
import FreqQueryView  from '../views/FreqQueryView.vue'
import FreqAssignView from '../views/FreqAssignView.vue'
import TaskView       from '../views/TaskView.vue'

const routes = [
  { path: '/',                    component: StationsView,  name: 'stations'   },
  { path: '/spectrum/:stationId', component: SpectrumView,  name: 'spectrum'   },
  { path: '/band-rules',          component: BandRulesView, name: 'band-rules' },
  { path: '/freq-query',          component: FreqQueryView, name: 'freq-query' },
  { path: '/freq-assign',         component: FreqAssignView,name: 'freq-assign'},
  { path: '/tasks',               component: TaskView,      name: 'tasks'      },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
