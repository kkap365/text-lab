import HomeView from '../components/HomeView';
import { useRouter } from 'next/router';

export default function Home() {
  const router = useRouter();
  const current = 'home';
  const onNavigate = (key) => {
    if (key === 'text-lab') {
      router.push('/text-lab');
    } else {
      router.push('/');
    }
  };
  return <HomeView current={current} onNavigate={onNavigate} />;
}
