import { useState } from 'react'
import { AppProvider, useApp } from './store'
import Sidebar from './components/Sidebar'
import ClassBrowser from './components/ClassBrowser'
import FlowGraph from './components/FlowGraph'
import DependencyView from './components/DependencyView'
import AgentChat from './components/AgentChat'
import WatchPanel from './components/WatchPanel'

function MainContent() {
  const [activeTab, setActiveTab] = useState('browser')
  const { t, theme, toggleTheme, lang, toggleLang } = useApp()

  const TABS = [
    { id: 'browser',    label: t('tab_browser') },
    { id: 'flow',       label: t('tab_flow') },
    { id: 'dependency', label: t('tab_dependency') },
    { id: 'watch',      label: t('tab_watch') },
    { id: 'agent',      label: t('tab_agent') },
  ]

  return (
    <div className="flex flex-col flex-1 overflow-hidden min-w-0">
      {/* 탭 헤더 */}
      <div className="flex border-b border-gray-800 bg-gray-950 shrink-0 overflow-x-auto items-stretch">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-3 text-sm font-medium transition-colors whitespace-nowrap shrink-0
              ${activeTab === tab.id ? 'tab-active' : 'tab-inactive'}`}
          >
            {tab.label}
          </button>
        ))}

        {/* 테마 · 언어 토글 (우측 고정) */}
        <div className="ml-auto flex items-center gap-1 px-2 shrink-0">
          <button
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            className="px-2 py-1 rounded text-sm hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
          >
            {theme === 'dark' ? t('theme_light') : t('theme_dark')}
          </button>
          <button
            onClick={toggleLang}
            title={lang === 'ko' ? 'Switch to English' : '한국어로 변경'}
            className="px-2 py-1 rounded text-xs font-medium hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors"
          >
            {t('lang_toggle')}
          </button>
        </div>
      </div>

      {/* 탭 콘텐츠 */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'browser'    && <ClassBrowser onFlowReady={() => setActiveTab('flow')} />}
        {activeTab === 'flow'       && <FlowGraph />}
        {activeTab === 'dependency' && <DependencyView />}
        {activeTab === 'watch'      && <WatchPanel />}
        {activeTab === 'agent'      && <AgentChat />}
      </div>
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <div className="flex h-screen overflow-hidden bg-gray-950">
        <Sidebar />
        <MainContent />
      </div>
    </AppProvider>
  )
}
