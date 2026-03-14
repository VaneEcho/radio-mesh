import { createRouter, createWebHistory } from 'vue-router'
import StationsView   from '../views/StationsView.vue'
import SpectrumView   from '../views/SpectrumView.vue'
import BandRulesView  from '../views/BandRulesView.vue'
import FreqQueryView  from '../views/FreqQueryView.vue'

const routes = [
  { path: '/',                    component: StationsView,  name: 'stations'  },
  { path: '/spectrum/:stationId', component: SpectrumView,  name: 'spectrum'  },
  { path: '/band-rules',          component: BandRulesView, name: 'band-rules'},
  { path: '/freq-query',          component: FreqQueryView, name: 'freq-query'},
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
