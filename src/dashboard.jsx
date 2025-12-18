import React from 'react';


const TimeAgo = ({ seconds }) => {
  if (seconds < 0) return <span className="text-gray-400">无更新记录</span>;
  if (seconds < 60) return <span className="text-green-600">最新</span>;
  if (seconds < 3600) return <span className="text-green-600">{Math.floor(seconds / 60)}min 前</span>;
  if (seconds < 86400) return <span className="text-gray-600">{Math.floor(seconds / 3600)}h 前</span>;
  return <span className="text-red-500">{Math.floor(seconds / 86400)}d 前</span>;
};

const StatusDot = ({ indicator }) => {
  const colors = {
    green: 'bg-green-500',
    yellow: 'bg-yellow-400 animate-pulse',
    red: 'bg-red-500',
    gray: 'bg-gray-300'
  };
  return <div className={`w-3 h-3 rounded-full ${colors[indicator] || colors.gray} mr-2`} />;
};

const Dashboard = ({ data = {}, onNavigate }) => {
  return (
    <div className="space-y-6 h-full flex flex-col p-8 overflow-y-auto">
      <h2 className="text-2xl font-bold text-gray-800 mb-4">System Overview</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Object.entries(data).map(([key, item]) => (
          <div 
            key={key} 
            onClick={() => onNavigate(key)}
            className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm hover:shadow-md hover:border-blue-300 transition-all cursor-pointer group"
          >
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-bold text-gray-700 capitalize text-lg">{key.replace('_', ' ')}</h3>
              <StatusDot indicator={item.indicator} />
            </div>
            <div className="text-sm text-gray-500 flex items-center">
              <span className="w-2 h-2 bg-gray-400 rounded-full mr-2 opacity-50"></span>
              Updated: <TimeAgo seconds={item.time_since} />
            </div>
            <div className="mt-4 text-xs text-blue-600 font-semibold group-hover:translate-x-1 transition-transform">
              Manage &rarr;
            </div>
          </div>
        ))}
      </div>
      
      <div className="mt-auto pt-6 border-t border-gray-100">
        <p className="text-xs text-gray-400 text-center">System Running Stable • Data Hub v1.0</p>
      </div>
    </div>
  );
};

export default Dashboard;