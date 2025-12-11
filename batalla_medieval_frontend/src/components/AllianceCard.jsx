const AllianceCard = ({ alliance, onCreate, onJoin }) => {
  const handleCreate = () => {
    const name = prompt('Nombre de la alianza');
    if (name) onCreate(name);
  };

  const handleJoin = () => {
    const code = prompt('Código de invitación');
    if (code) onJoin(code);
  };

  if (!alliance) {
    return (
      <div className="card p-4 flex flex-col gap-3 items-start">
        <h3 className="text-lg">Sin alianza</h3>
        <div className="flex gap-2">
          <button onClick={handleCreate} className="btn-primary">Crear alianza</button>
          <button onClick={handleJoin} className="btn-primary bg-gray-800 text-yellow-300">Unirse</button>
        </div>
      </div>
    );
  }

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xl">{alliance.name}</h3>
        <span className="badge">Miembros: {alliance.members?.length || 0}</span>
      </div>
      <ul className="text-sm text-gray-300 space-y-1">
        {alliance.members?.map((m) => (
          <li key={m.id} className="flex justify-between border-b border-gray-800 pb-1">
            <span>{m.username}</span>
            <span className="text-gray-400">{m.role}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default AllianceCard;
