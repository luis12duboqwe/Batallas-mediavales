import { useEffect, useState } from 'react';
import axiosClient from '../api/axiosClient';
import ReactMarkdown from 'react-markdown';

const WikiView = () => {
  const [articles, setArticles] = useState([]);
  const [selectedArticle, setSelectedArticle] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchArticles();
  }, []);

  const fetchArticles = () => {
    setLoading(true);
    axiosClient.get('/wiki/search')
      .then(res => {
        setArticles(res.data);
        if (res.data.length > 0) {
          setSelectedArticle(res.data[0]);
        }
      })
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  };

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col md:flex-row gap-6">
      {/* Sidebar List */}
      <div className="w-full md:w-1/3 lg:w-1/4 bg-black/20 rounded-xl border border-amber-900/30 overflow-hidden flex flex-col">
        <div className="p-4 border-b border-amber-900/30 bg-amber-900/10">
          <h2 className="text-xl font-bold text-amber-100">Enciclopedia</h2>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loading ? (
            <div className="p-4 text-center text-amber-500">Cargando...</div>
          ) : (
            articles.map(article => (
              <button
                key={article.id}
                onClick={() => setSelectedArticle(article)}
                className={`w-full text-left px-4 py-3 rounded-lg transition-colors ${
                  selectedArticle?.id === article.id 
                    ? 'bg-amber-700/30 text-amber-100 border border-amber-600/30' 
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }`}
              >
                <div className="font-medium">{article.title}</div>
                <div className="text-xs opacity-60 truncate">{article.category}</div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 bg-black/40 rounded-xl border border-amber-900/30 overflow-hidden flex flex-col">
        {selectedArticle ? (
          <div className="flex-1 overflow-y-auto p-6 md:p-8 custom-scrollbar">
            <div className="prose prose-invert prose-amber max-w-none">
              <h1 className="text-3xl font-bold text-amber-100 mb-2">{selectedArticle.title}</h1>
              <div className="flex gap-2 mb-6">
                <span className="badge badge-outline text-amber-400 border-amber-400/50">{selectedArticle.category}</span>
                <span className="text-xs text-gray-500 self-center">Actualizado: {new Date(selectedArticle.updated_at).toLocaleDateString()}</span>
              </div>
              <div className="bg-gray-900/50 p-6 rounded-xl border border-gray-800">
                <ReactMarkdown 
                  components={{
                    table: ({node, ...props}) => <div className="overflow-x-auto my-4"><table className="table table-zebra w-full" {...props} /></div>,
                    thead: ({node, ...props}) => <thead className="bg-amber-900/20 text-amber-200" {...props} />,
                    th: ({node, ...props}) => <th className="p-3 text-left" {...props} />,
                    td: ({node, ...props}) => <td className="p-3 border-b border-gray-800" {...props} />,
                  }}
                >
                  {selectedArticle.content_markdown}
                </ReactMarkdown>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            Selecciona un artículo para leer
          </div>
        )}
      </div>
    </div>
  );
};

export default WikiView;
