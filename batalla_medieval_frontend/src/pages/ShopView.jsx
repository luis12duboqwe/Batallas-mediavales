import { useEffect, useState } from 'react';
import axiosClient from '../api/axiosClient';
import { useUserStore } from '../store/userStore';

const ShopView = () => {
  const [items, setItems] = useState([]);
  const [myItems, setMyItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(null);
  const { user } = useUserStore(); // Assuming user store has rubies balance, if not we might need to fetch it

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [itemsRes, myItemsRes] = await Promise.all([
        axiosClient.get('/shop/items'),
        axiosClient.get('/shop/my_items')
      ]);
      setItems(Array.isArray(itemsRes.data) ? itemsRes.data : []);
      setMyItems(Array.isArray(myItemsRes.data) ? myItemsRes.data : []);
    } catch (error) {
      console.error(error);
      setItems([]);
      setMyItems([]);
    } finally {
      setLoading(false);
    }
  };

  const handleBuy = async (itemId) => {
    if (!confirm('¿Estás seguro de comprar este objeto?')) return;
    
    setBuying(itemId);
    try {
      await axiosClient.post(`/shop/buy/${itemId}`);
      alert('¡Compra exitosa!');
      fetchData(); // Refresh data
    } catch (error) {
      alert(error.response?.data?.detail || 'Error en la compra');
    } finally {
      setBuying(null);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-amber-100">Tienda</h1>
          <p className="text-amber-200/60">Adquiere ventajas y objetos especiales</p>
        </div>
        <div className="bg-amber-900/40 px-4 py-2 rounded-lg border border-amber-500/30">
          <span className="text-amber-200 text-sm uppercase mr-2">Rubíes:</span>
          <span className="text-xl font-bold text-amber-100">{user?.rubies_balance || 0} 💎</span>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <span className="loading loading-spinner text-amber-500"></span>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(item => (
              <div key={item.id} className="card bg-black/30 border border-amber-900/40 p-4 hover:border-amber-500/40 transition-colors">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="text-lg font-bold text-amber-100">{item.name}</h3>
                  <span className="badge badge-warning bg-amber-500/20 text-amber-200 border-amber-500/50">
                    {item.price} 💎
                  </span>
                </div>
                <p className="text-sm text-gray-400 mb-4 min-h-[3rem]">{item.description}</p>
                <button 
                  className="btn btn-primary w-full bg-gradient-to-r from-amber-700 to-yellow-700 border-none text-white"
                  onClick={() => handleBuy(item.id)}
                  disabled={buying === item.id}
                >
                  {buying === item.id ? 'Comprando...' : 'Comprar'}
                </button>
              </div>
            ))}
          </div>

          <div className="mt-12">
            <h2 className="text-2xl font-bold text-amber-100 mb-4">Mis Objetos</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {myItems.length === 0 && (
                <p className="text-gray-500 col-span-full">No tienes objetos en tu inventario.</p>
              )}
              {myItems.map((userItem, idx) => (
                <div key={idx} className="card bg-gray-900/40 border border-gray-700 p-3 flex flex-row items-center gap-3">
                  <div className="w-10 h-10 rounded bg-amber-900/20 flex items-center justify-center text-xl">
                    🎒
                  </div>
                  <div>
                    <p className="font-bold text-gray-200">{userItem.item?.name}</p>
                    <p className="text-xs text-gray-500">Adquirido: {new Date(userItem.acquired_at).toLocaleDateString()}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default ShopView;
