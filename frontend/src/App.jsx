// --------------- START OF FILE: ../frontend/src/App.jsx ---------------

import React, { useState, useEffect, useCallback } from 'react';

const API_URL = 'http://127.0.0.1:8000';

// --- STYLES COMPONENT (Integrated) ---
const GlobalStyles = () => (
    <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        :root {
            --primary-color: #2a6fdb;
            --primary-hover: #1e5a9b;
            --secondary-color: #6c757d;
            --background-color: #f8f9fa;
            --surface-color: #ffffff;
            --text-color: #212529;
            --border-color: #dee2e6;
            --danger-color: #dc3545;
            --danger-hover: #a71d2a;
            --success-color: #198754;
            --warning-color: #ffc107;
            --processing-color: #0dcaf0;
            --font-family: 'Inter', sans-serif;
        }
        body { font-family: var(--font-family); background-color: var(--background-color); color: var(--text-color); margin: 0; line-height: 1.6; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        .app-header { display: flex; justify-content: space-between; align-items: center; background-color: var(--surface-color); padding: 1.5rem 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); margin-bottom: 2rem; }
        .app-header h1 { font-size: 2rem; font-weight: 700; color: var(--primary-color); margin: 0; }
        .btn { padding: 0.75rem 1.5rem; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.2s ease-in-out; text-align: center; }
        .btn:disabled { background-color: var(--secondary-color); cursor: not-allowed; }
        .btn-primary { background-color: var(--primary-color); color: white; }
        .btn-primary:hover:not(:disabled) { background-color: var(--primary-hover); transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        .btn-danger { background-color: var(--danger-color); color: white; }
        .btn-danger:hover { background-color: var(--danger-hover); }
        .form-container { background-color: var(--surface-color); padding: 2.5rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); max-width: 500px; margin: 2rem auto; }
        .form-container h2 { text-align: center; margin-bottom: 2rem; font-size: 1.75rem; }
        .form-group { margin-bottom: 1.5rem; }
        .form-group label { display: block; margin-bottom: 0.5rem; font-weight: 500; color: var(--secondary-color); }
        .form-input { width: 100%; padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 8px; font-size: 1rem; box-sizing: border-box; }
        .form-input:focus { outline: none; border-color: var(--primary-color); box-shadow: 0 0 0 3px rgba(42, 111, 219, 0.2); }
        .form-checkbox { width: 1.25rem; height: 1.25rem; cursor: pointer; }
        .password-container { position: relative; display: flex; align-items: center; }
        .password-container .form-input { padding-right: 40px; }
        .password-toggle-btn { position: absolute; right: 10px; background: none; border: none; cursor: pointer; color: var(--secondary-color); padding: 0; display: flex; align-items: center; justify-content: center; }
        .error-message { background-color: rgba(220, 53, 69, 0.1); color: var(--danger-color); padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; text-align: center; }
        .success-message { background-color: rgba(25, 135, 84, 0.1); color: var(--success-color); padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; text-align: center; }
        .info-message { background-color: #eef2f7; color: #334d6e; padding: 1rem; border-radius: 8px; }
        .dashboard-layout { display: grid; grid-template-columns: 250px 1fr; gap: 2rem; }
        .dashboard-nav { background-color: var(--surface-color); padding: 1.5rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); align-self: start; }
        .dashboard-nav h3 { margin-top: 0; font-size: 1.25rem; }
        .nav-menu { display: flex; flex-direction: column; gap: 0.5rem; }
        .nav-button { text-align: left; padding: 0.75rem 1rem; border: none; background-color: transparent; border-radius: 8px; cursor: pointer; font-size: 1rem; font-weight: 500; width: 100%; transition: background-color 0.2s, color 0.2s; }
        .nav-button:hover { background-color: #f1f3f5; }
        .nav-button.active { background-color: var(--primary-color); color: white; }
        .dashboard-content { background-color: var(--surface-color); padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .dashboard-content h2 { margin-top: 0; margin-bottom: 2rem; font-size: 1.75rem; }
        .table-container { overflow-x: auto; border: 1px solid var(--border-color); border-radius: 12px; }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 1rem; text-align: left; border-bottom: 1px solid var(--border-color); white-space: normal; }
        .table thead th { background-color: #f8f9fa; font-weight: 600; }
        .table tbody tr:last-child td { border-bottom: none; }
        .table tbody tr:hover { background-color: #f1f3f5; }
        .filter-bar { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
        .capitalize { text-transform: capitalize; }
        .text-center { text-align: center; }
        .mt-1 { margin-top: 1rem; }
        .mt-2 { margin-top: 2rem; }
        .mb-1 { margin-bottom: 1rem; }
        .mb-2 { margin-bottom: 2rem; }
        
        /* --- JOB MONITOR STYLES --- */
        .job-monitor { background-color: var(--surface-color); padding: 2rem; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 2rem; }
        .job-monitor h3 { margin-top: 0; }
        .job-list { list-style-type: none; padding: 0; margin: 0; max-height: 400px; overflow-y: auto; }
        .job-item { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; padding: 1rem; border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 1rem; }
        .job-item:last-child { margin-bottom: 0; }
        .job-details { flex: 1; min-width: 200px; padding-right: 1rem; }
        .job-details strong { font-size: 1.1rem; }
        .job-status { display: flex; align-items: center; gap: 0.5rem; }
        .job-status-badge { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.25rem 0.75rem; border-radius: 20px; font-weight: 600; font-size: 0.9rem; }
        .job-status-processing { background-color: rgba(13, 202, 240, 0.1); color: var(--processing-color); }
        .job-status-complete { background-color: rgba(25, 135, 84, 0.1); color: var(--success-color); }
        .job-status-failed { background-color: rgba(220, 53, 69, 0.1); color: var(--danger-color); }
        .job-results-toggle { background: none; border: none; color: var(--primary-color); cursor: pointer; font-weight: 600; padding: 0.5rem; }
        .job-results-details { width: 100%; padding-top: 1rem; margin-top: 1rem; border-top: 1px solid var(--border-color); }
        .results-summary { font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem; }
        .results-list { list-style-type: none; padding: 0; max-height: 300px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: 8px; }
        .results-list li { display: flex; align-items: center; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); }
        .results-list li:last-child { border-bottom: none; }
        .result-icon { margin-right: 1rem; }
        .result-success .result-icon { color: var(--success-color); }
        .result-failure .result-icon { color: var(--danger-color); }
    `}</style>
);

const columnTranslations = {
    first_name: 'Prénom',
    last_name: 'Nom de famille',
    birth_date: 'Date de Naissance',
    delivery_date: 'Date de Délivrance',
    expiration_date: "Date d'Expiration",
    nationality: 'Nationalité',
    passport_number: 'Numéro de Passeport',
    confidence_score: 'Score de Confiance',
    email: 'Email',
    phone_number: 'Numéro de Téléphone',
    user_name: "Nom d'Utilisateur",
    role: 'Rôle',
    destination: 'Destination',
    token: 'Jeton',
    expires_at: 'Expire Le',
    is_used: 'Utilisé',
    actions: 'Actions'
};

// --- HELPER COMPONENTS & ICONS ---
const EyeIcon = () => (<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>);
const EyeOffIcon = () => (<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>);
function PasswordInput({ value, onChange, name, placeholder, required = false }) {
    const [showPassword, setShowPassword] = useState(false);
    return (
        <div className="password-container">
            <input type={showPassword ? 'text' : 'password'} name={name} value={value} onChange={onChange} className="form-input" placeholder={placeholder} required={required} autoComplete="new-password" />
            <button type="button" className="password-toggle-btn" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? 'Cacher le mot de passe' : 'Afficher le mot de passe'}>
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
            </button>
        </div>
    );
}

const SuccessIcon = () => (<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>);
const FailureIcon = () => (<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>);
const LoadingIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor" style={{ animation: 'spin 1s linear infinite' }}>
        <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
        <path d="M12,1A11,11,0,1,0,23,12,11,11,0,0,0,12,1Zm0,19a8,8,0,1,1,8-8A8,8,0,0,1,12,20Z" opacity=".25"/>
        <path d="M10.72,19.9a8,8,0,0,1-6.5-9.79A7.77,7.77,0,0,1,10.4,4.16a8,8,0,0,1,9.49,6.52A1.54,1.54,0,0,0,21.38,12h.13a1.37,1.37,0,0,0,1.38-1.54,11,11,0,1,0-12.7,12.7A1.54,1.54,0,0,0,12,21.34h0A1.47,1.47,0,0,0,10.72,19.9Z" />
    </svg>
);

// --- MAIN APP COMPONENT ---
export default function App() {
    const [token, setToken] = useState(localStorage.getItem('token'));
    const [user, setUser] = useState(null);
    const [view, setView] = useState('login');
    const logout = useCallback(() => { localStorage.removeItem('token'); setToken(null); setUser(null); window.history.pushState({}, '', '/'); setView('login'); }, []);
    const fetchUser = useCallback(async () => {
        const currentToken = localStorage.getItem('token');
        if (currentToken) {
            try {
                const response = await fetch(`${API_URL}/users/me`, { headers: { 'Authorization': `Bearer ${currentToken}` } });
                if (response.ok) { const data = await response.json(); setUser(data); setView('dashboard'); } else { logout(); }
            } catch (error) { console.error("Échec de la récupération de l'utilisateur:", error); logout(); }
        } else {
            const path = window.location.pathname;
            if (path.startsWith('/register/')) { setView('register'); } else { setView('login'); }
        }
    }, [logout]);
    useEffect(() => {
        fetchUser();
        const handlePopState = () => fetchUser();
        window.addEventListener('popstate', handlePopState);
        return () => window.removeEventListener('popstate', handlePopState);
    }, [fetchUser]);
    const renderView = () => {
        const path = window.location.pathname;
        if (view === 'register' || path.startsWith('/register/')) { const registrationToken = path.split('/')[2]; return <RegistrationPage registrationToken={registrationToken} />; }
        switch (view) {
            case 'login': return <Login setToken={setToken} fetchUser={fetchUser} />;
            case 'dashboard': return <Dashboard user={user} logout={logout} token={token} fetchUser={fetchUser} />;
            default: return <Login setToken={setToken} fetchUser={fetchUser} />;
        }
    };
    return (<><GlobalStyles /><div className="container"><header className="app-header"><h1>Gestionnaire de Voyages</h1>{user && <button onClick={logout} className="btn btn-danger">Déconnexion</button>}</header><main>{renderView()}</main></div></>);
}

// --- PAGE & VIEW COMPONENTS ---
function Login({ setToken, fetchUser }) {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);
        const formData = new URLSearchParams({ username, password });
        try {
            const response = await fetch(`${API_URL}/token`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: formData, });
            if (response.ok) {
                const data = await response.json();
                localStorage.setItem('token', data.access_token);
                setToken(data.access_token);
                fetchUser();
            } else {
                if (response.status === 429) {
                    setError("Trop de tentatives de connexion. Veuillez réessayer dans une minute.");
                } else {
                    const errorData = await response.json();
                    setError(errorData.detail || 'Échec de la connexion.');
                }
            }
        } catch (err) {
            setError('Une erreur est survenue. Veuillez réessayer.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="form-container">
            <h2>Connexion</h2>
            {error && <p className="error-message">{error}</p>}
            <form onSubmit={handleSubmit}>
                <div className="form-group">
                    <label>Nom d'utilisateur</label>
                    <input type="text" value={username} onChange={e => setUsername(e.target.value)} className="form-input" required />
                </div>
                <div className="form-group">
                    <label>Mot de passe</label>
                    <PasswordInput name="password" value={password} onChange={e => setPassword(e.target.value)} required={true} />
                </div>
                <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isLoading}>
                    {isLoading ? 'Connexion en cours...' : 'Se connecter'}
                </button>
            </form>
        </div>
    );
}

function RegistrationPage({ registrationToken }) {
    const [formData, setFormData] = useState({ first_name: '', last_name: '', email: '', phone_number: '', user_name: '', password: '' });
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    useEffect(() => {
        const fetchInvitation = async () => {
            if (!registrationToken) { setError("Aucun jeton d'inscription fourni."); setIsLoading(false); return; }
            try {
                const response = await fetch(`${API_URL}/invitations/${registrationToken}`);
                if (response.ok) { const data = await response.json(); setFormData(prev => ({ ...prev, email: data.email })); } else { setError((await response.json()).detail || "Lien d'inscription invalide ou expiré."); }
            } catch (err) { setError("Une erreur est survenue lors de la validation du lien d'inscription."); } finally { setIsLoading(false); }
        };
        fetchInvitation();
    }, [registrationToken]);
    const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });
    const handleSubmit = async (e) => {
        e.preventDefault(); setError(''); setSuccess('');
        try {
            const response = await fetch(`${API_URL}/users/?token=${registrationToken}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) });
            if (response.ok) { setSuccess('Inscription réussie ! Vous allez être redirigé vers la page de connexion.'); setTimeout(() => { window.history.pushState({}, '', '/'); window.location.reload(); }, 2000); } else { setError((await response.json()).detail || "Échec de l'inscription."); }
        } catch (err) { setError("Une erreur est survenue lors de l'inscription."); }
    };
    if (isLoading) return <p className="info-message">Chargement...</p>;
    if (success) return <div className="form-container"><p className="success-message">{success}</p></div>
    return (<div className="form-container"><h2>Créer un nouveau compte</h2>{error && <p className="error-message">{error}</p>}<form onSubmit={handleSubmit}><div className="form-group"><label>Prénom</label><input type="text" name="first_name" value={formData.first_name} onChange={handleChange} className="form-input" required /></div><div className="form-group"><label>Nom de famille</label><input type="text" name="last_name" value={formData.last_name} onChange={handleChange} className="form-input" required /></div><div className="form-group"><label>Email</label><input type="email" name="email" value={formData.email} onChange={handleChange} className="form-input" required readOnly /></div><div className="form-group"><label>Numéro de téléphone</label><input type="text" name="phone_number" value={formData.phone_number} onChange={handleChange} className="form-input" required /></div><div className="form-group"><label>Nom d'utilisateur</label><input type="text" name="user_name" value={formData.user_name} onChange={handleChange} className="form-input" required /></div><div className="form-group"><label>Mot de passe</label><PasswordInput name="password" value={formData.password} onChange={handleChange} required={true} /></div><button type="submit" className="btn btn-primary" style={{ width: '100%' }}>S'inscrire</button></form></div>);
}

function Dashboard({ user, token, fetchUser }) {
    const [activeTab, setActiveTab] = useState('account');
    const [filterableUsers, setFilterableUsers] = useState([]);
    const [userSpecificDestinations, setUserSpecificDestinations] = useState([]);

    const fetchAdminData = useCallback(async () => {
        if (user.role !== 'admin') return;
        try {
            const filterableUsersRes = await fetch(`${API_URL}/admin/filterable-users`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (filterableUsersRes.ok) setFilterableUsers(await filterableUsersRes.json());
        } catch (error) { console.error("Échec de la récupération des données admin:", error); }
    }, [user, token]);

    const fetchUserDestinations = useCallback(async () => {
        try {
            const response = await fetch(`${API_URL}/destinations/`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (response.ok) {
                setUserSpecificDestinations(await response.json());
            }
        } catch (error) {
            console.error("Échec de la récupération des destinations de l'utilisateur:", error);
        }
    }, [token]);

    useEffect(() => {
        fetchAdminData();
        fetchUserDestinations();
    }, [fetchAdminData, fetchUserDestinations]);

    const renderTabContent = () => {
        const passportFilterConfig = user.role === 'admin' 
            ? [{ name: 'user_filter', placeholder: 'Filtrer par Utilisateur', options: filterableUsers, getOptionValue: (o) => o.id, getOptionLabel: (o) => `${o.first_name} ${o.last_name} (${o.user_name})` }] 
            : null;

        const voyageFilterConfig = user.role === 'admin' 
            ? [{ name: 'user_filter', placeholder: 'Filtrer par Utilisateur', options: filterableUsers, getOptionValue: (o) => o.id, getOptionLabel: (o) => `${o.first_name} ${o.last_name} (${o.user_name})` }] 
            : null;
            
        const passportFields = { first_name: 'text', last_name: 'text', birth_date: 'date', delivery_date: 'date', expiration_date: 'date', nationality: 'text', passport_number: 'text', destination: 'text', confidence_score: 'number' };
        
        switch (activeTab) {
            case 'account': return <AccountEditor user={user} token={token} fetchUser={fetchUser} />;
            case 'passports': return <CrudManager title="Gérer les Passeports" endpoint="passports" token={token} user={user} fields={passportFields} filterConfig={passportFilterConfig} />;
            case 'voyages': return <CrudManager title="Gérer les Voyages" endpoint="voyages" token={token} user={user} fields={{ destination: 'text' }} filterConfig={voyageFilterConfig} />;
            case 'tools_export': return <ToolsAndExportPanel token={token} user={user} adminUsers={filterableUsers} userDestinations={userSpecificDestinations} />;
            case 'users': return user.role === 'admin' ? <CrudManager title="Gérer les Utilisateurs" endpoint="admin/users" token={token} user={user} fields={{ first_name: 'text', last_name: 'text', email: 'email', phone_number: 'text', user_name: 'text', password: 'password', role: 'text' }} /> : null;
            case 'invitations': return user.role === 'admin' ? <CrudManager title="Gérer les Invitations" endpoint="admin/invitations" token={token} user={user} fields={{ email: 'email', token: 'text', expires_at: 'datetime-local', is_used: 'checkbox' }} /> : null;
            default: return null;
        }
    };
    return (
        <div className="dashboard-layout">
            <nav className="dashboard-nav">
                <h3>Bienvenue, {user.first_name}!</h3>
                <div className="nav-menu">
                    <button onClick={() => setActiveTab('account')} className={`nav-button ${activeTab === 'account' ? 'active' : ''}`}>Mon Compte</button>
                    <button onClick={() => setActiveTab('passports')} className={`nav-button ${activeTab === 'passports' ? 'active' : ''}`}>Passeports</button>
                    <button onClick={() => setActiveTab('voyages')} className={`nav-button ${activeTab === 'voyages' ? 'active' : ''}`}>Voyages</button>
                    <button onClick={() => setActiveTab('tools_export')} className={`nav-button ${activeTab === 'tools_export' ? 'active' : ''}`}>Outils & Exportation</button>
                    {user.role === 'admin' && (
                        <>
                            <hr />
                            <button onClick={() => setActiveTab('users')} className={`nav-button ${activeTab === 'users' ? 'active' : ''}`}>Gérer les Utilisateurs</button>
                            <button onClick={() => setActiveTab('invitations')} className={`nav-button ${activeTab === 'invitations' ? 'active' : ''}`}>Gérer les Invitations</button>
                        </>
                    )}
                </div>
            </nav>
            <div className="dashboard-content">{renderTabContent()}</div>
        </div>
    );
}

// --- DASHBOARD SUB-COMPONENTS ---
function AccountEditor({ user, token, fetchUser }) {
    const [formData, setFormData] = useState({ first_name: '', last_name: '', email: '', phone_number: '', password: '' });
    const [message, setMessage] = useState('');
    useEffect(() => { if (user) setFormData({ first_name: user.first_name, last_name: user.last_name, email: user.email, phone_number: user.phone_number, password: '' }); }, [user]);
    const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });
    const handleSubmit = async (e) => {
        e.preventDefault(); setMessage(''); const payload = { ...formData }; if (!payload.password) delete payload.password;
        const response = await fetch(`${API_URL}/users/me`, { method: 'PUT', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(payload) });
        if (response.ok) { setMessage('Compte mis à jour avec succès !'); fetchUser(); } else { setMessage('Échec de la mise à jour du compte.'); }
    };
    return (<div><h2>Modifier Mon Compte</h2>{message && <p className="success-message">{message}</p>}<form onSubmit={handleSubmit}><div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}><div className="form-group"><label>Prénom</label><input type="text" name="first_name" value={formData.first_name} onChange={handleChange} className="form-input" /></div><div className="form-group"><label>Nom de famille</label><input type="text" name="last_name" value={formData.last_name} onChange={handleChange} className="form-input" /></div><div className="form-group"><label>Email</label><input type="email" name="email" value={formData.email} onChange={handleChange} className="form-input" /></div><div className="form-group"><label>Numéro de téléphone</label><input type="text" name="phone_number" value={formData.phone_number} onChange={handleChange} className="form-input" /></div></div><div className="form-group"><label>Nouveau mot de passe (optionnel)</label><PasswordInput name="password" value={formData.password} onChange={handleChange} placeholder="Laisser vide pour conserver le mot de passe actuel" /></div><button type="submit" className="btn btn-primary">Enregistrer les modifications</button></form></div>);
}

// --- OcrUploader ---
function OcrUploader({ token, onUploadSuccess, onCancel }) {
    const [file, setFile] = useState(null);
    const [isUploading, setIsUploading] = useState(false);
    const [error, setError] = useState('');
    const [destination, setDestination] = useState('');
    const [destinations, setDestinations] = useState([]);

    useEffect(() => {
        const fetchDestinations = async () => {
            try {
                const response = await fetch(`${API_URL}/destinations/`, {
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    setDestinations(await response.json());
                }
            } catch (error) {
                console.error("Échec de la récupération des destinations:", error);
            }
        };
        fetchDestinations();
    }, [token]);

    const handleFileChange = (e) => {
        setFile(e.target.files[0]);
        setError('');
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!file) {
            setError('Veuillez sélectionner un fichier à télécharger.');
            return;
        }

        setIsUploading(true);
        setError('');

        const formData = new FormData();
        formData.append('file', file);
        if (destination) {
            formData.append('destination', destination);
        }

        try {
            const response = await fetch(`${API_URL}/passports/upload-and-extract/`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData,
            });

            if (response.ok) {
                onUploadSuccess();
            } else {
                const data = await response.json();
                setError(data.detail || "Échec du démarrage du job de téléchargement.");
            }
        } catch (err) {
            setError('Une erreur inattendue est survenue. Veuillez réessayer.');
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className="form-container" style={{ maxWidth: 'none', margin: 0, padding: '2rem' }}>
            <h3>Ajouter un Passeport via Téléchargement de Document</h3>
            <p className="mb-2" style={{ color: 'var(--secondary-color)' }}>
                Téléchargez une image claire ou un PDF. Le traitement se fera en arrière-plan et l'état apparaîtra dans le moniteur de suivi.
            </p>

            {error && <p className="error-message">{error}</p>}

            <form onSubmit={handleSubmit}>
                <div className="form-group">
                    <label>Destination (Optionnel)</label>
                    <input
                        type="text"
                        name="destination"
                        value={destination}
                        onChange={(e) => setDestination(e.target.value)}
                        className="form-input"
                        list="destination-datalist-ocr"
                        placeholder="Choisissez ou créez une destination pour tous les passeports de ce fichier"
                        autoComplete="off"
                    />
                    <datalist id="destination-datalist-ocr">
                        {destinations.map(dest => <option key={dest} value={dest} />)}
                    </datalist>
                </div>

                <div className="form-group">
                    <label>Document de Passeport (Image ou PDF)</label>
                    <input
                        type="file"
                        onChange={handleFileChange}
                        accept="image/png, image/jpeg, image/jpg, application/pdf"
                        className="form-input"
                        required
                        disabled={isUploading}
                    />
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '2rem' }}>
                    <button type="button" onClick={onCancel} className="btn" style={{ backgroundColor: 'var(--secondary-color)', color: 'white' }} disabled={isUploading}>Annuler</button>
                    <button type="submit" className="btn btn-primary" disabled={isUploading || !file}>
                        {isUploading ? 'Démarrage...' : 'Télécharger et Extraire'}
                    </button>
                </div>
            </form>
        </div>
    );
}


// --- OcrJobMonitor (MODIFIED) ---
function OcrJobMonitor({ token }) {
    const [jobs, setJobs] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState('');
    const [expandedJobId, setExpandedJobId] = useState(null);
    // const [hiddenJobIds, setHiddenJobIds] = useState(new Set()); // <-- No longer needed

    const fetchJobs = useCallback(async () => {
        try {
            const response = await fetch(`${API_URL}/ocr/jobs/`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                const data = await response.json();
                setJobs(data);
            } else {
                setError('Échec de la récupération des jobs OCR.');
            }
        } catch (err) {
            setError('Une erreur est survenue lors de la récupération des jobs.');
        } finally {
            setIsLoading(false);
        }
    }, [token]);
    
    useEffect(() => {
        // Fetch immediately on mount
        fetchJobs();
        
        // Set an interval to poll every 5 seconds.
        const interval = setInterval(fetchJobs, 5000); 

        // Cleanup interval on unmount
        return () => clearInterval(interval);
    }, [fetchJobs]);


    const toggleJobDetails = (jobId) => {
        setExpandedJobId(prev => (prev === jobId ? null : jobId));
    };

    // --- UPDATED HANDLER ---
    // This function now calls the DELETE endpoint and removes the job from local state.
    const handleRemoveJob = async (jobIdToRemove) => {
        setExpandedJobId(null); // Close the modal
        try {
            const response = await fetch(`${API_URL}/ocr/jobs/${jobIdToRemove}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.ok) {
                // Remove the job from the local state for immediate UI update
                setJobs(prevJobs => prevJobs.filter(job => job.id !== jobIdToRemove));
            } else {
                // Handle error (e.g., show a temporary error message)
                console.error("Failed to delete job");
                setError("Échec de la suppression du job."); // Show error in the monitor
            }
        } catch (err) {
            console.error("Error deleting job:", err);
            setError("Une erreur est survenue lors de la suppression du job.");
        }
    };

    const formatDate = (dateString) => {
        if (!dateString) return '';
        return new Date(dateString).toLocaleString('fr-FR', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
    };

    if (isLoading) return <p className="info-message">Chargement des jobs de Télétraitement...</p>;
    if (error) return <p className="error-message">{error}</p>;

    // We now render directly from the `jobs` state
    return (
        <div className="job-monitor">
            <h3>Suivi des Téléchargements de Passeports</h3>
            {jobs.length === 0 ? (
                <p className="info-message">Aucun document n'a encore été téléchargé.</p>
            ) : (
                <ul className="job-list">
                    {jobs.map(job => (
                        <li key={job.id} className="job-item">
                            <div className="job-details">
                                <strong>{job.file_name}</strong>
                                <br />
                                <small style={{ color: 'var(--secondary-color)' }}>
                                    {formatDate(job.created_at)}
                                </small>
                            </div>
                            <div className="job-status">
                                {job.status === 'processing' && (
                                    <span className="job-status-badge job-status-processing">
                                        <LoadingIcon /> Traitement...
                                    </span>
                                )}
                                {job.status === 'complete' && (
                                    <span className="job-status-badge job-status-complete">
                                        Terminé
                                    </span>
                                )}
                                {job.status === 'failed' && (
                                    <span className="job-status-badge job-status-failed">
                                        Échoué
                                    </span>
                                )}
                            </div>
                            {job.status !== 'processing' && (
                                <button className="job-results-toggle" onClick={() => toggleJobDetails(job.id)}>
                                    {expandedJobId === job.id ? 'Cacher' : 'Voir'} les Résultats
                                </button>
                            )}
                            
                            {expandedJobId === job.id && (
                                <div className="job-results-details">
                                    <p className="results-summary">
                                        Traitement Terminé : {job.successes.length} réussis, {job.failures.length} échoués.
                                    </p>
                                    <ul className="results-list">
                                        {job.successes.map(success => (
                                            <li key={success.data.id} className="result-success">
                                                <span className="result-icon"><SuccessIcon /></span>
                                                <span><b>Page {success.page_number}</b> traitée : Passeport créé pour <b>{success.data.first_name} {success.data.last_name}</b> (N° : {success.data.passport_number}).</span>
                                            </li>
                                        ))}
                                        {job.failures.map((failure, index) => (
                                            <li key={index} className="result-failure">
                                                <span className="result-icon"><FailureIcon /></span>
                                                <span><b>La page {failure.page_number} a échoué :</b> {failure.detail}</span>
                                            </li>
                                        ))}
                                    </ul>
                                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
                                        <button 
                                            onClick={() => handleRemoveJob(job.id)} 
                                            className="btn btn-danger"
                                        >
                                            Supprimer
                                        </button>
                                    </div>
                                </div>
                            )}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}


function CrudManager({ title, endpoint, token, user, fields, filterConfig }) {
    const [items, setItems] = useState([]);
    const [editingItem, setEditingItem] = useState(null);
    const [isCreating, setIsCreating] = useState(false);
    const [filters, setFilters] = useState({});
    const [showOcrUploader, setShowOcrUploader] = useState(false);
    const [dynamicDestinations, setDynamicDestinations] = useState([]);

    const fetchDestinationsForUser = useCallback(async (userId) => {
        const query = userId ? `?user_id=${userId}` : '';
        try {
            const response = await fetch(`${API_URL}/destinations/${query}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (response.ok) {
                setDynamicDestinations(await response.json());
            }
        } catch (error) {
            console.error("Échec de la récupération des destinations:", error);
        }
    }, [token]);

    useEffect(() => {
        if (user.role === 'admin' && endpoint === 'passports') {
            fetchDestinationsForUser(null);
        }
    }, [user, endpoint, fetchDestinationsForUser]);

    const handleFilterChange = (filterName, value) => {
        const newFilters = { ...filters, [filterName]: value };
        if (user.role === 'admin' && filterName === 'user_filter') {
            fetchDestinationsForUser(value || null);
            newFilters.voyage_filter = '';
        }
        setFilters(newFilters);
    };

    const fetchData = useCallback(async () => {
        const activeFilters = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
        const query = new URLSearchParams(activeFilters);
        const url = `${API_URL}/${endpoint}/?${query.toString()}`;
        try {
            const response = await fetch(url, { headers: { 'Authorization': `Bearer ${token}` } });
            if (response.ok) setItems(await response.json());
            else console.error("Échec de la récupération des données pour", endpoint);
        } catch (error) { console.error("Erreur lors de la récupération des données:", error); }
    }, [endpoint, token, filters]);
    
    useEffect(() => { fetchData(); }, [fetchData]);

    const handleDelete = async (id) => {
        if (window.confirm('Êtes-vous sûr de vouloir supprimer cet élément ?')) {
            await fetch(`${API_URL}/${endpoint}/${id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token}` } });
            fetchData();
        }
    };
    
    const handleSave = () => { 
        setEditingItem(null); 
        setIsCreating(false); 
        setShowOcrUploader(false); 
        fetchData(); 
    };

    const startCreating = () => {
        let newItem = Object.keys(fields).reduce((acc, key) => ({ ...acc, [key]: '' }), {});
        if (endpoint === 'admin/users') newItem.role = 'user';
        if (endpoint === 'admin/invitations') newItem = { email: '' };
        setEditingItem(newItem);
        setIsCreating(true);
    };

    if (showOcrUploader) {
        return <OcrUploader 
            token={token} 
            onUploadSuccess={handleSave} 
            onCancel={() => setShowOcrUploader(false)} 
        />
    }

    if (editingItem) return <CrudForm item={editingItem} isCreating={isCreating} onSave={handleSave} onCancel={() => setEditingItem(null)} fields={fields} endpoint={endpoint} token={token} />;

    const displayFields = { ...fields };
    if (endpoint === 'admin/users') delete displayFields.password;
    if (endpoint === 'admin/invitations' && isCreating) delete displayFields.token;
    if (endpoint === 'passports') delete displayFields.destination;

    return (
        <div>
            {endpoint === 'passports' && <OcrJobMonitor token={token} />}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }} className="mb-2">
                <h2>{title}</h2>
                <div style={{ display: 'flex', gap: '1rem' }}>
                    {endpoint === 'passports' && (
                        <button onClick={() => setShowOcrUploader(true)} className="btn btn-primary" style={{ backgroundColor: 'var(--success-color)' }}>
                            + Ajouter par Téléchargement
                        </button>
                    )}
                    <button onClick={startCreating} className="btn btn-primary">
                        {endpoint === 'passports' ? '+ Ajouter Manuellement' : '+ Ajouter'}
                    </button>
                </div>
            </div>

            {endpoint.includes('users') && !filterConfig && (
                <div className="filter-bar mb-2"><div className="form-group" style={{ flex: 1, marginBottom: 0 }}><input type="text" name="name_filter" placeholder="Filtrer par Nom, Nom d'utilisateur ou Email" onChange={(e) => handleFilterChange(e.target.name, e.target.value)} className="form-input" autoComplete="off"/></div></div>
            )}
            
            {filterConfig && (
                <div className="filter-bar mb-2">
                    {filterConfig.map(filter => (
                        <ComboBoxFilter key={filter.name} {...filter} onChange={handleFilterChange} />
                    ))}
                    {user.role === 'admin' && endpoint === 'passports' && (
                         <ComboBoxFilter 
                            key="voyage_filter" 
                            name="voyage_filter"
                            placeholder="Filtrer par Destination"
                            options={dynamicDestinations.map(d => ({ destination: d }))}
                            getOptionValue={(o) => o.destination}
                            getOptionLabel={(o) => o.destination}
                            onChange={handleFilterChange} 
                        />
                    )}
                </div>
            )}

            <div className="table-container">
                <table className="table">
                    <thead>
                        <tr>
                            {Object.keys(displayFields).map(field => (
                                <th key={field}>{columnTranslations[field] || field.replace(/_/g, ' ')}</th>
                            ))}
                            <th>{columnTranslations['actions']}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map(item => (
                            <tr key={item.id}>
                                {Object.keys(displayFields).map(field => {
                                    let cellValue = item[field];
                                    if (field === 'confidence_score' && typeof cellValue === 'number') { cellValue = `${(cellValue * 100).toFixed(2)}%`; }
                                    return <td key={field}>{String(cellValue)}</td>
                                })}
                                <td>
                                    <button onClick={() => setEditingItem(item)} className="btn" style={{ backgroundColor: 'var(--warning-color)', color: 'black', marginRight: '0.5rem' }}>Modifier</button>
                                    <button onClick={() => handleDelete(item.id)} className="btn btn-danger">Supprimer</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

// --- (Rest of the file is unchanged) ---

function CrudForm({ item, isCreating, onSave, onCancel, fields, endpoint, token }) {
    const [formData, setFormData] = useState(item);
    const [destinations, setDestinations] = useState([]);
    const [error, setError] = useState('');
    useEffect(() => {
        const initialData = { ...item };
        Object.entries(fields).forEach(([key, type]) => { if (type === 'datetime-local' && initialData[key]) { initialData[key] = new Date(initialData[key]).toISOString().slice(0, 16); } });
        if (endpoint === 'passports' && !isCreating && item.voyages && item.voyages.length > 0) { initialData.destination = item.voyages[0].destination; }
        setFormData(initialData);
    }, [item, fields, endpoint, isCreating]);
    
    useEffect(() => {
        if (endpoint === 'passports') {
            const fetchDestinations = async () => {
                try {
                    const response = await fetch(`${API_URL}/destinations/`, { headers: { 'Authorization': `Bearer ${token}` } });
                    if (response.ok) setDestinations(await response.json());
                } catch (error) { console.error("Échec de la récupération des destinations:", error); }
            };
            fetchDestinations();
        }
    }, [endpoint, token]);

    const handleChange = (e) => { const { name, value, type, checked } = e.target; setFormData({ ...formData, [name]: type === 'checkbox' ? checked : value }); };
    const handleSubmit = async (e) => {
        e.preventDefault(); setError('');
        let url = isCreating ? `${API_URL}/${endpoint}/` : `${API_URL}/${endpoint}/${item.id}`;
        let method = isCreating ? 'POST' : 'PUT';
        let body = { ...formData };
        if (body.confidence_score === '') { body.confidence_score = null; }
        if (endpoint === 'admin/invitations' && isCreating) body = { email: formData.email };
        if (endpoint === 'admin/users' && !isCreating && !body.password) delete body.password;
        const response = await fetch(url, { method, headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(body), });
        if (response.ok) { onSave(); } else { 
            const errorData = await response.json(); 
            setError(errorData.detail || "Échec de l'enregistrement de l'élément."); 
        }
    };
    const formFields = { ...fields };
    if (formFields.confidence_score) { delete formFields.confidence_score; }
    if (isCreating && endpoint === 'admin/invitations') { return (<form onSubmit={handleSubmit} className="form-container" style={{ maxWidth: 'none', margin: 0, padding: '2rem' }}><h3>Créer une nouvelle invitation</h3>{error && <p className="error-message">{error}</p>}<div className="form-group"><label>Email</label><input type="email" name="email" value={formData.email || ''} onChange={handleChange} className="form-input" required /></div><div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '2rem' }}><button type="button" onClick={onCancel} className="btn" style={{ backgroundColor: 'var(--secondary-color)', color: 'white' }}>Annuler</button><button type="submit" className="btn btn-primary">Enregistrer</button></div></form>) }
    return (<form onSubmit={handleSubmit} className="form-container" style={{ maxWidth: 'none', margin: 0, padding: '2rem' }}><h3>{isCreating ? 'Créer' : 'Modifier'} l'élément</h3>{error && <p className="error-message">{error}</p>}<div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>{Object.entries(formFields).map(([key, type]) => (<div className="form-group" key={key}><label>{columnTranslations[key] || key.replace(/_/g, ' ')}</label>{key === 'password' ? (<PasswordInput name={key} value={formData[key] || ''} onChange={handleChange} placeholder={!isCreating ? 'Laisser vide pour conserver' : ''} required={isCreating} />) : key === 'destination' ? (<><input type="text" name="destination" value={formData.destination || ''} onChange={handleChange} className="form-input" list="destination-datalist-form" placeholder="Choisissez ou créez une destination" autoComplete="off" /><datalist id="destination-datalist-form">{destinations.map(dest => <option key={dest} value={dest} />)}</datalist></>) : type === 'checkbox' ? (<input type="checkbox" name={key} checked={!!formData[key]} onChange={handleChange} className="form-checkbox" />) : (<input type={type} name={key} value={formData[key] || ''} onChange={handleChange} className="form-input" required={key !== 'destination' && key !== 'token' && type !== 'checkbox'} readOnly={(key === 'token')} />)}</div>))}</div><div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '2rem' }}><button type="button" onClick={onCancel} className="btn" style={{ backgroundColor: 'var(--secondary-color)', color: 'white' }}>Annuler</button><button type="submit" className="btn btn-primary">Enregistrer</button></div></form>);
}

function ToolsAndExportPanel({ token, user, adminUsers, userDestinations }) {
    const [filters, setFilters] = useState({ user_id: '', destination: '' });
    const [previewData, setPreviewData] = useState(null);
    const [inviteEmail, setInviteEmail] = useState('');
    const [inviteMsg, setInviteMsg] = useState('');
    const [invitationLink, setInvitationLink] = useState('');

    const handleFilterChange = (name, value) => { 
        setFilters(prev => ({ ...prev, [name]: value })); 
        setPreviewData(null); 
    };

    const getFilteredData = async () => {
        const activeFilters = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
        if (user.role !== 'admin') {
            delete activeFilters.user_id;
        }
        const query = new URLSearchParams(activeFilters).toString();
        try {
            const response = await fetch(`${API_URL}/export/data?${query}`, { headers: { 'Authorization': `Bearer ${token}` } });
            if (!response.ok) { 
                const err = await response.json();
                alert(`Échec de la récupération des données: ${err.detail}`); 
                return null; 
            }
            return response;
        } catch (error) { alert('Une erreur est survenue lors de la récupération des données.'); return null; }
    };

    const handlePreview = async () => {
        const response = await getFilteredData();
        if (response) {
            const csvText = await response.text();
            if (!csvText) { setPreviewData([]); return; }
            const rows = csvText.trim().split('\n');
            const headers = rows[0].split(',');
            const data = rows.slice(1).map(row => { const values = row.split(','); return headers.reduce((obj, h, i) => ({ ...obj, [h]: values[i] }), {}); });
            setPreviewData(data);
        }
    };
    
    const handleExport = async () => {
        const response = await getFilteredData();
        if (response) {
            const blob = await response.blob();
            const contentDisposition = response.headers.get('content-disposition');
            const filename = contentDisposition?.match(/filename="?(.+)"?/)?.[1] || 'passports_export.csv';
            const url = window.URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
            setPreviewData(null);
        }
    };

    const handleInvite = async () => {
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(inviteEmail)) { setInviteMsg('Veuillez entrer une adresse email valide.'); return; }
        setInviteMsg('Génération du lien...'); setInvitationLink('');
        try {
            const response = await fetch(`${API_URL}/admin/invitations`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ email: inviteEmail }), });
            const data = await response.json();
            if (response.ok) { const link = `${window.location.origin}/register/${data.token}`; setInvitationLink(link); setInviteMsg('Lien généré. Copiez-le et envoyez-le à l\'utilisateur.'); } else { setInviteMsg(data.detail || 'Échec de la création de l\'invitation.'); }
        } catch (error) { setInviteMsg('Une erreur est survenue.'); }
    };

    return (
        <div>
            <h2>Outils & Exportation</h2>
            {user.role === 'admin' && (
                <div className="form-container" style={{ maxWidth: 'none', margin: 0, padding: '2rem', marginBottom: '2rem' }}>
                    <h3>Inviter un nouvel utilisateur</h3>
                    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                        <input type="email" placeholder="Entrez l'email de l'utilisateur" value={inviteEmail} onChange={e => setInviteEmail(e.target.value)} className="form-input" style={{ flexGrow: 1 }} />
                        <button onClick={handleInvite} className="btn btn-primary" style={{ backgroundColor: 'var(--warning-color)', color: 'black' }}>Générer le lien</button>
                    </div>
                    {inviteMsg && <p className="info-message mt-1">{inviteMsg}</p>}
                    {invitationLink && (
                        <div className="mt-1">
                            <input type="text" readOnly value={invitationLink} className="form-input" onClick={e => e.target.select()} />
                        </div>
                    )}
                </div>
            )}
            <div className="form-container" style={{ maxWidth: 'none', margin: 0, padding: '2rem' }}>
                <h3>Filtrer et Exporter les Données des Passeports</h3>
                <div className="filter-bar mb-1">
                    {user.role === 'admin' && (
                        <ComboBoxFilter 
                            name="user_id" 
                            placeholder="Filtrer par Utilisateur" 
                            options={adminUsers} 
                            getOptionValue={(o) => o.id} 
                            getOptionLabel={(o) => `${o.first_name} ${o.last_name} (${o.user_name})`} 
                            onChange={handleFilterChange} 
                        />
                    )}
                     <ComboBoxFilter 
                        name="destination" 
                        placeholder="Filtrer par Destination" 
                        options={userDestinations.map(d => ({ destination: d }))} 
                        getOptionValue={(o) => o.destination} 
                        getOptionLabel={(o) => o.destination} 
                        onChange={handleFilterChange} 
                    />
                </div>
                <button onClick={handlePreview} className="btn btn-primary">Aperçu des Données</button>
                {previewData && (
                    <>
                        <PreviewTable data={previewData} />
                        <button onClick={handleExport} className="btn mt-1" style={{ backgroundColor: 'var(--success-color)', color: 'white' }}>Télécharger en CSV</button>
                    </>
                )}
            </div>
        </div>
    );
}

function ComboBoxFilter({ name, placeholder, options, getOptionValue, getOptionLabel, onChange }) {
    const dataListId = `datalist-${name}-${Math.random()}`;
    return (
        <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <input 
                list={dataListId} 
                name={name} 
                placeholder={placeholder} 
                onChange={(e) => onChange(name, e.target.value)} 
                className="form-input"
                autoComplete="off"
            />
            <datalist id={dataListId}>
                <option value="">-- Aucun --</option> 
                {options.map(option => (
                    <option key={getOptionValue(option)} value={getOptionValue(option)}>
                        {getOptionLabel(option)}
                    </option>
                ))}
            </datalist>
        </div>
    );
}

function PreviewTable({ data }) {
    if (!data || data.length === 0) return <p className="mt-2 text-center info-message">Aucune donnée à prévisualiser pour les filtres sélectionnés.</p>;
    const headers = Object.keys(data[0]);
    return (<div className="mt-2"><h3 className="mb-1">Aperçu des Données</h3><div className="table-container"><table className="table"><thead><tr>{headers.map(h => <th key={h}>{columnTranslations[h] || h.replace(/_/g, ' ')}</th>)}</tr></thead><tbody>{data.map((row, i) => <tr key={i}>{headers.map(h => <td key={h}>{String(row[h])}</td>)}</tr>)}</tbody></table></div></div>);
}

// --------------- END OF FILE: ../frontend/src/App.jsx ---------------