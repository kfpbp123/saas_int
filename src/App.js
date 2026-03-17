import React, { useState, useEffect } from 'react';
import axios from 'axios';

// Используем localhost для тестов, если не задана переменная окружения
const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [user, setUser] = useState(null);
  const [queue, setQueue] = useState([]);
  const [activeTab, setActiveTab] = useState('home');
  
  // Безопасное получение объекта Telegram
  const [tg] = useState(window.Telegram?.WebApp || null);

  // Если открыто в браузере, используем твой ID для тестов
  const userId = tg?.initDataUnsafe?.user?.id || 5703605946; 

  useEffect(() => {
    if (tg) {
        tg.expand();
        tg.ready();
    }
    fetchData();
    // eslint-disable-next-line
  }, []);

  const fetchData = async () => {
    try {
      console.log("Fetching from:", `${API_BASE}/api/user/${userId}`);
      const userRes = await axios.get(`${API_BASE}/api/user/${userId}`);
      setUser(userRes.data);
      const queueRes = await axios.get(`${API_BASE}/api/queue/${userId}`);
      setQueue(queueRes.data);
    } catch (err) {
      console.error("API Error (Make sure Python backend is running!):", err);
      // Если API недоступно, создадим "фейковые" данные для теста интерфейса
      if (!user) {
          setUser({
              username: "Preview User",
              tier: "free",
              used: 5,
              limit: 30,
              isPro: false
          });
      }
    }
  };

  const deletePost = async (postId) => {
    if (window.confirm("Delete this post?")) {
      try {
          await axios.delete(`${API_BASE}/api/queue/${postId}?tg_id=${userId}`);
          fetchData();
      } catch(e) { alert("Error deleting post"); }
    }
  };

  if (!user) return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center text-white">
        <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-400 mx-auto mb-4"></div>
            <p className="text-emerald-400 font-medium">MineBot Studio is waking up...</p>
        </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans pb-24 overflow-x-hidden">
      {/* Header */}
      <div className="p-6 bg-slate-800 border-b border-slate-700 shadow-xl sticky top-0 z-50">
        <div className="flex justify-between items-center">
            <div>
                <h1 className="text-2xl font-bold text-emerald-400 tracking-tight">MineBot Studio</h1>
                <p className="text-slate-400 text-xs mt-0.5">Control Center • {user.username || 'User'}</p>
            </div>
            <div className="h-10 w-10 bg-emerald-500/10 rounded-full flex items-center justify-center border border-emerald-500/20">
                <span className="text-xl">🤖</span>
            </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="p-4 max-w-md mx-auto">
        {activeTab === 'home' && (
          <div className="space-y-6 animate-fadeIn">
            {/* Stats Card */}
            <div className="bg-slate-800 p-6 rounded-3xl shadow-2xl border border-slate-700 relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-10">
                <span className="text-6xl">📊</span>
              </div>
              
              <div className="flex justify-between items-center mb-6">
                <span className="text-slate-400 uppercase text-[10px] font-black tracking-[0.2em]">Monthly Usage</span>
                <span className={`px-3 py-1 rounded-full text-[10px] font-black tracking-wider uppercase ${user.isPro ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
                  {user.tier}
                </span>
              </div>
              
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-5xl font-black text-white">{user.used}</span>
                <span className="text-slate-500 text-xl font-bold">/ {user.limit}</span>
              </div>
              
              <div className="w-full bg-slate-700/50 h-3 rounded-full overflow-hidden backdrop-blur-sm">
                <div 
                  className="bg-gradient-to-r from-emerald-600 to-emerald-400 h-full transition-all duration-1000 ease-out" 
                  style={{ width: `${Math.min((user.used / user.limit) * 100, 100)}%` }}
                ></div>
              </div>
              <p className="text-slate-500 text-[11px] mt-4 font-medium">Your limit resets in 12 days</p>
            </div>
            
            <button className="w-full py-5 bg-gradient-to-br from-emerald-600 to-emerald-700 hover:from-emerald-500 hover:to-emerald-600 rounded-2xl font-black text-sm uppercase tracking-widest shadow-lg shadow-emerald-900/20 transition-all active:scale-95">
              💎 Upgrade to Pro
            </button>

            {/* Quick Tips */}
            <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-800/50 p-4 rounded-2xl border border-slate-700/50">
                    <span className="text-xl mb-2 block">📝</span>
                    <h3 className="text-xs font-bold text-white mb-1">Queue</h3>
                    <p className="text-[10px] text-slate-500">Manage scheduled mods</p>
                </div>
                <div className="bg-slate-800/50 p-4 rounded-2xl border border-slate-700/50">
                    <span className="text-xl mb-2 block">📈</span>
                    <h3 className="text-xs font-bold text-white mb-1">Analytics</h3>
                    <p className="text-[10px] text-slate-500">View post insights</p>
                </div>
            </div>
          </div>
        )}

        {activeTab === 'queue' && (
          <div className="space-y-4 animate-fadeIn">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-black text-white">Upcoming <span className="text-emerald-400">Posts</span></h2>
                <span className="bg-slate-800 px-3 py-1 rounded-lg text-xs font-bold text-slate-400 border border-slate-700">{queue.length} items</span>
            </div>
            
            {queue.map(post => (
              <div key={post.id} className="bg-slate-800/80 backdrop-blur-sm p-5 rounded-2xl border border-slate-700/50 flex justify-between items-center group transition-all hover:border-emerald-500/30">
                <div className="flex-1 pr-6">
                  <p className="text-sm font-medium text-slate-200 line-clamp-2 leading-relaxed mb-3">{post.text || 'Untitled Post'}</p>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                        <span className="text-[10px]">🕒</span>
                        <span className="text-[10px] font-bold text-slate-400">
                          {new Date(post.scheduled_time * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="text-[10px]">📢</span>
                        <span className="text-[10px] font-bold text-emerald-500/80">
                          {post.channel || '@default'}
                        </span>
                    </div>
                  </div>
                </div>
                <button 
                  onClick={() => deletePost(post.id)}
                  className="h-10 w-10 bg-red-500/10 text-red-500 rounded-xl flex items-center justify-center transition-all hover:bg-red-500 hover:text-white active:scale-90"
                >
                  <span className="text-lg">🗑</span>
                </button>
              </div>
            ))}
            
            {queue.length === 0 && (
                <div className="py-20 text-center">
                    <span className="text-5xl opacity-20 grayscale block mb-4">📭</span>
                    <p className="text-slate-500 font-bold uppercase text-[10px] tracking-widest">Queue is absolutely empty</p>
                </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-slate-900/80 backdrop-blur-xl border-t border-slate-800/50 flex justify-around p-3 pb-8 z-50">
        {[
            {id: 'home', icon: '🏠', label: 'Dashboard'},
            {id: 'queue', icon: '📅', label: 'Queue'},
            {id: 'shop', icon: '💎', label: 'Pro'}
        ].map(tab => (
            <button 
                key={tab.id}
                onClick={() => setActiveTab(tab.id)} 
                className={`flex flex-col items-center min-w-[60px] transition-all duration-300 ${activeTab === tab.id ? 'text-emerald-400 scale-110' : 'text-slate-500'}`}
            >
                <span className={`text-2xl mb-1 ${activeTab === tab.id ? 'drop-shadow-[0_0_8px_rgba(52,211,153,0.5)]' : ''}`}>
                    {tab.icon}
                </span>
                <span className={`text-[9px] font-black uppercase tracking-tighter ${activeTab === tab.id ? 'opacity-100' : 'opacity-60'}`}>
                    {tab.label}
                </span>
                {activeTab === tab.id && (
                    <div className="w-1 h-1 bg-emerald-400 rounded-full mt-1 animate-pulse"></div>
                )}
            </button>
        ))}
      </div>
    </div>
  );
}

export default App;
